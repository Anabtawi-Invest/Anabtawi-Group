/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        this.pos_cake_order_id = vals?.pos_cake_order_id || null;
        this.pos_cake_product_id = vals?.pos_cake_product_id || null;
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        this.syncPosCakeLinkFromLines();
        if (this.pos_cake_order_id) {
            data.pos_cake_order_id = this.pos_cake_order_id;
        }
        return data;
    },

    setPosCakeOrderId(cakeOrderId, cakeProductId = null) {
        this.pos_cake_order_id = cakeOrderId || null;
        this.pos_cake_product_id = cakeProductId || null;
    },

    clearPosCakeOrderId() {
        this.pos_cake_order_id = null;
        this.pos_cake_product_id = null;
    },

    hasLinkedCakeProduct() {
        if (!this.pos_cake_order_id) {
            return true;
        }
        // After a POS reload we may only have the cake order id. Keep the link and
        // let the backend validate on payment.
        if (!this.pos_cake_product_id) {
            return true;
        }
        const cakeProductId = Number(this.pos_cake_product_id);
        return this.lines.some((line) => Number(line.product_id?.id) === cakeProductId);
    },

    syncPosCakeLinkFromLines() {
        if (!this.pos_cake_order_id || !this.pos_cake_product_id) {
            return Boolean(this.pos_cake_order_id);
        }
        if (this.hasLinkedCakeProduct()) {
            return true;
        }
        this.clearPosCakeOrderId();
        return false;
    },

    removeOrderline(line, deep = true) {
        const result = super.removeOrderline(line, deep);
        this.syncPosCakeLinkFromLines();
        return result;
    },
});
