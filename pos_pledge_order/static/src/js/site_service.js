/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import {
    computeSiteServiceScoreFromLines,
    getSiteServiceConfig,
    normalizeId,
} from "@pos_advance_order/js/site_service_utils";

/** @type {import("@point_of_sale/app/services/pos_store").PosStore | null} */
let posStoreRef = null;

function resolvePos(order) {
    return order?._siteServicePos || posStoreRef;
}

function attachPosToOrder(order, pos) {
    if (order && pos) {
        order._siteServicePos = pos;
    }
}

function computeSiteServiceScore(order, menuConfig) {
    const orderLines = order.lines || (order.getOrderlines?.() || []);
    const lines = orderLines.map((orderLine) => ({
        product_id: normalizeId(orderLine.getProduct?.() || orderLine.product_id || orderLine.product),
        qty: orderLine.getQuantity?.() ?? orderLine.qty ?? 0,
        is_site_service_auto: orderLine.is_site_service_auto,
    }));
    return computeSiteServiceScoreFromLines(lines, menuConfig);
}

function getSiteServiceAutoLines(order) {
    const orderLines = order.lines || (order.getOrderlines?.() || []);
    return orderLines.filter((line) => line.is_site_service_auto);
}

async function addSiteServiceLine(pos, order, menuConfig, serviceProduct) {
    attachPosToOrder(order, pos);
    return pos.addLineToOrder(
        {
            product_id: serviceProduct,
            product_tmpl_id: serviceProduct.product_tmpl_id,
            qty: 1,
            price_unit: menuConfig.servicePrice,
            price_type: "manual",
        },
        order,
        { force: true },
        false
    );
}

async function syncSiteServiceLine(pos, order) {
    if (!order || order._syncingSiteService) {
        return;
    }
    attachPosToOrder(order, pos);
    const menuConfig = getSiteServiceConfig(pos);
    order._syncingSiteService = true;
    try {
        for (const line of getSiteServiceAutoLines(order)) {
            order.removeOrderline(line);
        }
        if (!menuConfig) {
            return;
        }
        const score = computeSiteServiceScore(order, menuConfig);
        if (score >= menuConfig.threshold) {
            console.info(
                `[SITE_SERVICE] Score ${score} >= threshold ${menuConfig.threshold}; service waived.`
            );
            return;
        }
        const serviceProduct = pos.models["product.product"].get(menuConfig.serviceProductId);
        if (!serviceProduct) {
            console.warn(
                `[SITE_SERVICE] Service product id=${menuConfig.serviceProductId} not found in POS data for config id=${pos.config?.id}`
            );
            return;
        }
        const addedLine = await addSiteServiceLine(pos, order, menuConfig, serviceProduct);
        const line = addedLine || order.getSelectedOrderline?.();
        if (line) {
            line.is_site_service_auto = true;
        }
        console.info(
            `[SITE_SERVICE] Added service line (score=${score}, threshold=${menuConfig.threshold}).`
        );
    } catch (error) {
        console.error(
            `[SITE_SERVICE] Failed to sync site service line for order id=${order.id}, config id=${pos.config?.id}:`,
            error
        );
    } finally {
        order._syncingSiteService = false;
    }
}

function scheduleSiteServiceSync(order) {
    if (!order || order._syncingSiteService) {
        return;
    }
    const pos = resolvePos(order);
    if (!pos) {
        return;
    }
    syncSiteServiceLine(pos, order).catch((error) => {
        console.error(`[SITE_SERVICE] Unhandled sync error for order id=${order.id}:`, error);
    });
}

patch(PosStore.prototype, {
    async setup(...args) {
        await super.setup(...args);
        posStoreRef = this;
    },

    async addLineToOrder(vals, order, opts = {}, configure = true) {
        if (order) {
            attachPosToOrder(order, this);
        }
        const result = await super.addLineToOrder(vals, order, opts, configure);
        if (order && !order._syncingSiteService) {
            await syncSiteServiceLine(this, order);
        }
        return result;
    },

    async addLineToCurrentOrder(vals, opts = {}, configure = true) {
        const order = this.getOrder();
        if (order) {
            attachPosToOrder(order, this);
        }
        const result = await super.addLineToCurrentOrder(vals, opts, configure);
        if (order && !order._syncingSiteService) {
            await syncSiteServiceLine(this, order);
        }
        return result;
    },
});

patch(PosOrderline.prototype, {
    setup(vals) {
        super.setup(vals);
        this.is_site_service_auto = vals?.is_site_service_auto || false;
    },

    setQuantity(quantity, keep_price) {
        const result = super.setQuantity(...arguments);
        scheduleSiteServiceSync(this.order_id);
        return result;
    },
});

patch(PosOrder.prototype, {
    removeOrderline(line) {
        const result = super.removeOrderline(...arguments);
        if (!this._syncingSiteService) {
            scheduleSiteServiceSync(this);
        }
        return result;
    },
});

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        const order = this.pos.selectedOrder;
        if (order) {
            attachPosToOrder(order, this.pos);
            await syncSiteServiceLine(this.pos, order);
        }
        return super.validateOrder(isForceValidate);
    },
});
