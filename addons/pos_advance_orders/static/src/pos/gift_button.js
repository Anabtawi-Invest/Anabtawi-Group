/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class GiftLineButton extends Component {
    static template = "pos_advance_orders.GiftLineButton";

    onClick() {
        const pos = this.env.services.pos;
        const order = pos.get_order();
        const line = order.get_selected_orderline();
        if (!line) {
            return;
        }

        // If already gift → restore original price
        if (line.is_gift) {
            const original = line.gift_original_price_unit || line.get_unit_price();
            line.set_unit_price(original);
            line.is_gift = false;
            line.gift_original_price_unit = 0;
            return;
        }

        // Store original price and set to zero
        line.gift_original_price_unit = line.get_unit_price();
        line.set_unit_price(0);
        line.is_gift = true;
    }
}

// ✅ CORRECT way to register a POS control button
registry.category("pos_screens").add("GiftLineButton", {
    component: GiftLineButton,
    condition() {
        return true;
    },
});
