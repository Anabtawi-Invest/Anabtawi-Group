/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/store/models";

/**
 * Ensure extra fields are included when orders are pushed to the backend.
 */
patch(Order.prototype, {
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.pos_adv_is_advance_order = this.pos_adv_is_advance_order || false;
        json.pos_adv_requested_datetime = this.pos_adv_requested_datetime || false; // ISO string or false
        json.pos_adv_note = this.pos_adv_note || "";
        return json;
    },
});
