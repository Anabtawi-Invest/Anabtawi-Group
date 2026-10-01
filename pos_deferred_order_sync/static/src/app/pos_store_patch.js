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
        if (!order.finalized || order.isSynced) {
            return true;
        }
        if (order.isToInvoice?.()) {
            return true;
        }
        // pos_custom_cake, pos_scheduled_orders, pos_pledge_order
        if (order.pos_cake_order_id || order.fulfillment_type || order.hasPledge || order.pledgeData) {
            return true;
        }
        return order.lines.some(
            (line) =>
                line.refunded_orderline_id ||
                line.is_onsite_auto_pledge_line ||
                line.product_id?.is_employee_service
        );
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
            return await super.syncAllOrders(...arguments);
        }
        if (this.isFlushingDeferredOrders) {
            return await super.syncAllOrders({ ...options, force: true });
        }

        const { orderToCreate, orderToUpdate } = this.getPendingOrder();
        const candidates = options.orders || [...orderToCreate, ...orderToUpdate];
        const ordersToSync = new Set();
        let includesRefundedOriginals = false;
        for (const order of candidates) {
            if (!this.mustSyncOrderImmediately(order)) {
                continue;
            }
            // The refunded order must exist on the server before its refund.
            for (const original of this.getUnsyncedRefundedOrders(order)) {
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
