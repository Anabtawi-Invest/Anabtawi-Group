/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.open_amount = Number(vals.open_amount) || 0;
    },

    getOpenAmount() {
        return Math.max(Number(this.open_amount) || 0, 0);
    },

    get currencyOpenAmount() {
        return this.currency.format(this.getOpenAmount());
    },

    setOpenAmount(value) {
        this.update({ open_amount: Math.max(Number(value) || 0, 0) });
        this.trigger?.("change", this);
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        data.open_amount = this.getOpenAmount();
        return data;
    },
});
