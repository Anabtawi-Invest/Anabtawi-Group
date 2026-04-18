/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { formatCurrency } from "@web/core/currency";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.open_amount = Number(vals.open_amount) || 0;
    },

    getOpenAmount() {
        return Math.max(Number(this.open_amount) || 0, 0);
    },

    get currencyOpenAmount() {
        return formatCurrency(this.getOpenAmount(), this.currency.id);
    },

    setOpenAmount(value) {
        this.update({ open_amount: Math.max(Number(value) || 0, 0) });
        this.triggerRecomputeAllPrices();
        this.trigger?.("change", this);
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        data.open_amount = this.getOpenAmount();
        return data;
    },

    _constructPriceData(opts = {}) {
        const data = super._constructPriceData(opts);
        const openAmount = this.getOpenAmount();
        if (!openAmount) {
            return data;
        }

        data.taxDetails.total_amount_no_rounding -= openAmount;
        data.taxDetails.total_amount -= openAmount;
        return data;
    },
});
