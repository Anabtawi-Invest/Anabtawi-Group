/** @odoo-module **/

import { PosComponent } from "@point_of_sale/app/core/pos_component";
import { registry } from "@web/core/registry";
import { useState } from "@odoo/owl";

export class AdvanceOrderNativeScreen extends PosComponent {
    static template = "pos_advance_order_posnative.AdvanceOrderNativeScreen";

    setup() {
        super.setup();
        const order = this.pos.get_order();
        this.state = useState({
            adv_type: order?.pos_adv_type || "pickup",
            requested_datetime: order?.pos_adv_requested_datetime || "",
            contact_name: order?.pos_adv_contact_name || "",
            phone: order?.pos_adv_phone || "",
            address: order?.pos_adv_address || "",
            note: order?.pos_adv_note || "",
            deposit: (order?.pos_adv_deposit ?? 0).toString(),
        });
    }

    back() {
        this.pos.showScreen("ProductScreen");
    }

    clear() {
        const order = this.pos.get_order();
        if (order) {
            order.pos_adv_is_advance_order = false;
            order.pos_adv_type = "pickup";
            order.pos_adv_requested_datetime = false;
            order.pos_adv_contact_name = "";
            order.pos_adv_phone = "";
            order.pos_adv_address = "";
            order.pos_adv_note = "";
            order.pos_adv_deposit = 0;
        }
        this.state.adv_type = "pickup";
        this.state.requested_datetime = "";
        this.state.contact_name = "";
        this.state.phone = "";
        this.state.address = "";
        this.state.note = "";
        this.state.deposit = "0";
    }

    save() {
        const order = this.pos.get_order();
        if (!order) return this.back();

        const deposit = parseFloat(this.state.deposit || "0") || 0;

        order.pos_adv_is_advance_order = true;
        order.pos_adv_type = this.state.adv_type || "pickup";
        order.pos_adv_requested_datetime = this.state.requested_datetime || false;
        order.pos_adv_contact_name = this.state.contact_name || "";
        order.pos_adv_phone = this.state.phone || "";
        order.pos_adv_address = this.state.address || "";
        order.pos_adv_note = this.state.note || "";
        order.pos_adv_deposit = deposit;

        this.back();
    }
}

registry.category("pos_screens").add("AdvanceOrderNativeScreen", AdvanceOrderNativeScreen);
