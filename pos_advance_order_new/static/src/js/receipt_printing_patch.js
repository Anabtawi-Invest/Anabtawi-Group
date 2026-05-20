/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/store/models";

/**
 * Add advance-order info to receipt printing context.
 */
patch(Order.prototype, {
    export_for_printing() {
        const res = super.export_for_printing(...arguments);
        res.pos_adv_is_advance_order = this.pos_adv_is_advance_order || false;
        res.pos_adv_type = this.pos_adv_type || "pickup";
        res.pos_adv_requested_datetime = this.pos_adv_requested_datetime || false;
        res.pos_adv_contact_name = this.pos_adv_contact_name || "";
        res.pos_adv_phone = this.pos_adv_phone || "";
        res.pos_adv_address = this.pos_adv_address || "";
        res.pos_adv_note = this.pos_adv_note || "";
        res.pos_adv_deposit = this.pos_adv_deposit || 0;
        return res;
    },
});
