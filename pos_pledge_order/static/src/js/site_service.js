/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

function normalizeId(value) {
    if (!value) {
        return null;
    }
    if (typeof value === "number") {
        return value;
    }
    if (Array.isArray(value)) {
        return value[0] || null;
    }
    if (typeof value === "object" && value.id) {
        return value.id;
    }
    return null;
}

function getSiteServiceConfig(pos) {
    const config = pos?.config;
    if (!config) {
        return null;
    }
    const menuModel = pos.models?.["pos.site.service.menu"];
    if (!menuModel) {
        console.warn(
            `[SITE_SERVICE] Model pos.site.service.menu is missing from POS data (config id=${config.id})`
        );
        return null;
    }
    const menu = (menuModel?.getAll?.() || []).find(
        (record) => record.enable_site_service
    );
    if (!menu) {
        return null;
    }
    const serviceProductId = normalizeId(menu.service_product_id);
    if (!serviceProductId) {
        return null;
    }
    const lineModel = pos.models?.["pos.site.service.product.line"];
    const productLines = (lineModel?.getAll?.() || []).filter(
        (line) => normalizeId(line.menu_id) === menu.id
    );
    return {
        threshold: menu.threshold ?? 31,
        serviceProductId,
        servicePrice: menu.service_price ?? 0,
        productLines,
    };
}

function computeSiteServiceScore(order, menuConfig) {
    const multiplesByProduct = new Map();
    for (const line of menuConfig.productLines) {
        const productId = normalizeId(line.product_id);
        if (productId) {
            multiplesByProduct.set(productId, line.multiple || 0);
        }
    }
    let score = 0;
    const orderLines = order.getOrderlines ? order.getOrderlines() : order.lines || [];
    for (const orderLine of orderLines) {
        if (orderLine.is_site_service_auto) {
            continue;
        }
        const product = orderLine.getProduct?.() || orderLine.product_id || orderLine.product;
        const productId = normalizeId(product);
        if (!productId || !multiplesByProduct.has(productId)) {
            continue;
        }
        const qty = orderLine.get_quantity?.() ?? orderLine.qty ?? 0;
        score += qty * multiplesByProduct.get(productId);
    }
    return score;
}

function getSiteServiceAutoLines(order) {
    const orderLines = order.getOrderlines ? order.getOrderlines() : order.lines || [];
    return orderLines.filter((line) => line.is_site_service_auto);
}

async function syncSiteServiceLine(pos, order) {
    if (!order || order._syncingSiteService) {
        return;
    }
    order._siteServicePos = pos;
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
            return;
        }
        const serviceProduct = pos.models["product.product"].get(menuConfig.serviceProductId);
        if (!serviceProduct) {
            console.warn(
                `[SITE_SERVICE] Service product id=${menuConfig.serviceProductId} not found in POS data for config id=${pos.config?.id}`
            );
            return;
        }
        const addedLine = await pos.addLineToOrder(
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
        const line = addedLine || order.getSelectedOrderline?.();
        if (line) {
            line.is_site_service_auto = true;
        }
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
    const pos = order?._siteServicePos;
    if (!order || !pos || order._syncingSiteService) {
        return;
    }
    syncSiteServiceLine(pos, order).catch((error) => {
        console.error(
            `[SITE_SERVICE] Unhandled sync error for order id=${order.id}:`,
            error
        );
    });
}

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
        scheduleSiteServiceSync(this);
        return result;
    },
});

patch(PosStore.prototype, {
    async addLineToOrder(vals, order, opts = {}, configure = true) {
        if (order) {
            order._siteServicePos = this;
        }
        const result = await super.addLineToOrder(vals, order, opts, configure);
        if (order && !order._syncingSiteService) {
            await syncSiteServiceLine(this, order);
        }
        return result;
    },
});

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        const order = this.pos.selectedOrder;
        if (order) {
            order._siteServicePos = this.pos;
            await syncSiteServiceLine(this.pos, order);
        }
        return super.validateOrder(isForceValidate);
    },
});
