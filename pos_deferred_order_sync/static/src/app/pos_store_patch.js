/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    get isDeferredOrderSyncEnabled() {
        return Boolean(this.config?.deferred_order_sync);
    },

    get isFlushingDeferredOrders() {
        return (this._deferredOrderFlushDepth || 0) > 0;
    },

    getDeferredOrders() {
        return this.models["pos.order"].filter((order) => order.isUnsyncedPaid);
    },

    /**
     * Orders that must reach the server right away even when deferral is on,
     * because a server-side flow depends on them during the session.
     */
    mustSyncOrderImmediately(order) {
        return Boolean(this.getImmediateSyncReason(order));
    },

    /**
     * Returns why the order must be sent now, or null if it can wait until closing.
     */
    getImmediateSyncReason(order) {
        if (!order.finalized) {
            return `draft order (state: ${order.state})`;
        }
        if (order.isSynced) {
            return "already saved on the server";
        }
        if (order.isToInvoice?.()) {
            return "invoice requested";
        }
        if (order.pos_cake_order_id) {
            return "custom cake order";
        }
        if (order.fulfillment_type) {
            return `scheduled order (${order.fulfillment_type})`;
        }
        if (order.hasPledge || order.pledgeData) {
            return "pledge / employee service order (pos_pledge_order)";
        }
        for (const line of order.lines) {
            const productName = line.product_id?.display_name || line.product_id?.name || "";
            if (line.refunded_orderline_id) {
                return `refund line: ${productName}`;
            }
            if (line.is_onsite_auto_pledge_line) {
                return `auto pledge line (pos_onsite_price): ${productName}`;
            }
            if (line.product_id?.is_employee_service) {
                return `employee service product: ${productName}`;
            }
        }
        return null;
    },

    logDeferredSync(message, ...details) {
        console.info(`[DEFERRED_SYNC] ${message}`, ...details);
    },

    getUnsyncedRefundedOrders(order) {
        const originals = new Set();
        for (const line of order.lines) {
            const original = line.refunded_orderline_id?.order_id;
            if (original && !original.isSynced) {
                originals.add(original);
            }
        }
        return [...originals];
    },

    async withDeferredOrdersFlush(callback) {
        this._deferredOrderFlushDepth = (this._deferredOrderFlushDepth || 0) + 1;
        try {
            return await callback();
        } finally {
            this._deferredOrderFlushDepth -= 1;
        }
    },

    async syncAllOrders(options = {}) {
        if (!this.isDeferredOrderSyncEnabled) {
            this.logDeferredSync(
                `disabled on POS config "${this.config?.name}" (deferred_order_sync=${this.config?.deferred_order_sync}) - normal sync`
            );
            return await super.syncAllOrders(...arguments);
        }
        if (this.isFlushingDeferredOrders) {
            this.logDeferredSync(
                `closing session - sending ${this.getDeferredOrders().length} held order(s)`
            );
            return await super.syncAllOrders({ ...options, force: true });
        }

        const { orderToCreate, orderToUpdate } = this.getPendingOrder();
        const candidates = options.orders || [...orderToCreate, ...orderToUpdate];
        const ordersToSync = new Set();
        let includesRefundedOriginals = false;
        for (const order of candidates) {
            const reason = this.getImmediateSyncReason(order);
            if (!reason) {
                this.logDeferredSync(`HELD until closing: ${order.pos_reference || order.name}`, order);
                continue;
            }
            this.logDeferredSync(
                `SENT NOW: ${order.pos_reference || order.name} - reason: ${reason}`,
                order
            );
            // The refunded order must exist on the server before its refund.
            for (const original of this.getUnsyncedRefundedOrders(order)) {
                this.logDeferredSync(
                    `SENT NOW: ${original.pos_reference || original.name} - reason: original of refund ${order.pos_reference || order.name}`
                );
                ordersToSync.add(original);
                includesRefundedOriginals = true;
            }
            ordersToSync.add(order);
        }

        if (!ordersToSync.size && !this.getOrderIdsToDelete().length) {
            return [];
        }
        const result = await super.syncAllOrders({
            ...options,
            orders: [...ordersToSync],
            force: options.force || includesRefundedOriginals,
        });
        // Callers (e.g. payment validation) treat a falsy result as a failure.
        return result || [];
    },

    async pushOrdersWithClosingPopup(opts = {}) {
        if (!this.isDeferredOrderSyncEnabled || this._isLeavingWithoutClosing) {
            return await super.pushOrdersWithClosingPopup(...arguments);
        }
        const deferredOrderIds = this.getDeferredOrders().map((order) => order.id);
        if (deferredOrderIds.length) {
            this.addPendingOrder(deferredOrderIds);
        }
        // Without `throw`, failed orders are skipped silently and the push reports success.
        return await this.withDeferredOrdersFlush(() =>
            super.pushOrdersWithClosingPopup({ throw: true, ...opts })
        );
    },

    async closePos() {
        // Exiting to the backend keeps held orders on the device; only closing the session sends them.
        this._isLeavingWithoutClosing = true;
        try {
            return await super.closePos(...arguments);
        } finally {
            this._isLeavingWithoutClosing = false;
        }
    },

    async closingSessionNotification() {
        return await this.withDeferredOrdersFlush(() =>
            super.closingSessionNotification(...arguments)
        );
    },

    async closeSession() {
        // Closing totals are read from the server, so held orders must be sent first.
        if (this.isDeferredOrderSyncEnabled && this.getDeferredOrders().length) {
            const synced = await this.pushOrdersWithClosingPopup();
            if (!synced) {
                return;
            }
        }
        return await super.closeSession(...arguments);
    },
});
