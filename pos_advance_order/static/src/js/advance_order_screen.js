/** @odoo-module **/

import { PosComponent } from "@point_of_sale/app/core/pos_component";
import { registry } from "@web/core/registry";
import { useState } from "@odoo/owl";

/**
 * Advance order screen:
 * - captures requested date/time + note
 * - saves values on current Order (client side)
 * - values are sent to backend via export_as_JSON patch
 */
export class AdvanceOrderScreen extends PosComponent {
    static template = "pos_advance_order_html.AdvanceOrderScreen";

    setup() {
        super.setup();
        const order = this.pos.get_order();

        this.state = useState({
            requested_datetime: order?.pos_adv_requested_datetime || "",
            note: order?.pos_adv_note || "",
        });
    }

    back() {
        this.pos.showScreen("ProductScreen");
    }

    save() {
        const order = this.pos.get_order();
        if (!order) {
            this.back();
            return;
        }

        order.pos_adv_is_advance_order = true;
        order.pos_adv_requested_datetime = this.state.requested_datetime || false;
        order.pos_adv_note = this.state.note || "";

        this.back();
    }

    clear() {
        const order = this.pos.get_order();
        if (order) {
            order.pos_adv_is_advance_order = false;
            order.pos_adv_requested_datetime = false;
            order.pos_adv_note = "";
        }
        this.state.requested_datetime = "";
        this.state.note = "";
    }
}

registry.category("pos_screens").add("AdvanceOrderScreen", AdvanceOrderScreen);
