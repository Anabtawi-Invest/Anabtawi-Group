/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/store/models";

patch(Order.prototype, {
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.pos_adv_is_advance_order = this.pos_adv_is_advance_order || false;
        json.pos_adv_type = this.pos_adv_type || "pickup";
        json.pos_adv_requested_datetime = this.pos_adv_requested_datetime || false;
        json.pos_adv_contact_name = this.pos_adv_contact_name || "";
        json.pos_adv_phone = this.pos_adv_phone || "";
        json.pos_adv_address = this.pos_adv_address || "";
        json.pos_adv_note = this.pos_adv_note || "";
        json.pos_adv_deposit = this.pos_adv_deposit || 0;
        return json;
    },
});
