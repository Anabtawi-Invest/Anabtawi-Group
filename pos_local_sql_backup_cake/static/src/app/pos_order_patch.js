/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        this.pos_cake_local_uuid = vals?.pos_cake_local_uuid || null;
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        // Never send a synthetic negative cake id to Odoo.
        if (data.pos_cake_order_id && Number(data.pos_cake_order_id) < 0) {
            delete data.pos_cake_order_id;
        }
        return data;
    },
});
