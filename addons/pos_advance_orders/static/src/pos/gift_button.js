/** @odoo-module **/

import { Component } from "@odoo/owl";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

export class GiftLineButton extends Component {
    static template = "pos_advance_orders.GiftLineButton";

    onClick() {
        const order = this.env.services.pos.get_order();
        const line = order.get_selected_orderline();
        if (!line) return;

        // If already gift => restore
        if (line.is_gift) {
            const original = line.gift_original_price_unit || line.get_unit_price();
            line.set_unit_price(original);
            line.is_gift = false;
            line.gift_original_price_unit = 0;
            return;
        }

        // store original, set to zero
        line.gift_original_price_unit = line.get_unit_price();
        line.set_unit_price(0);
        line.is_gift = true;
    }
}

ProductScreen.addControlButton({
    component: GiftLineButton,
    condition() {
        return true;
    },
});
