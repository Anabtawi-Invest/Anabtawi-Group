/** @odoo-module **/

import { Component } from "@odoo/owl";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { useService } from "@web/core/utils/hooks";
import { DiscountPopup } from "./discount_popup";

export class DiscountButton extends Component {
    static template = "pos_advance_orders.DiscountButton";

    setup() {
        this.popup = useService("popup");
    }

    async onClick() {
        await this.popup.add(DiscountPopup, {});
    }
}

ProductScreen.addControlButton({
    component: DiscountButton,
    condition() {
        return true;
    },
});
