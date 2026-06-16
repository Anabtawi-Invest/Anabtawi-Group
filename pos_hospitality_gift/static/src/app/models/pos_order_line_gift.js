/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

patch(PosOrderline.prototype, {
    setup(vals) {
        super.setup(vals);
        this.is_gift = Boolean(vals?.is_gift);
        this.gift_reason = vals?.gift_reason || "";
    },

    getDisplayClasses() {
        return {
            ...super.getDisplayClasses(),
            o_pos_line_gift: Boolean(this.is_gift),
        };
    },

    canBeMergedWith(orderline) {
        if (Boolean(this.is_gift) !== Boolean(orderline?.is_gift)) {
            return false;
        }
        return super.canBeMergedWith(orderline);
    },
});
