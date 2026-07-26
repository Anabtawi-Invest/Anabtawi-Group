/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        this.pos_cake_order_id = vals?.pos_cake_order_id || null;
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        if (this.pos_cake_order_id) {
            data.pos_cake_order_id = this.pos_cake_order_id;
        }
        return data;
    },

    setPosCakeOrderId(cakeOrderId) {
        this.pos_cake_order_id = cakeOrderId;
    },
});
