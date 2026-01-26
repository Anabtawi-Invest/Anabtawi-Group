/** @odoo-module **/

import { Component } from "@odoo/owl";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { useService } from "@web/core/utils/hooks";
import { AdvanceOrdersPopup } from "./advance_orders_popup";

export class AdvanceOrdersButton extends Component {
    static template = "pos_advance_orders.AdvanceOrdersButton";

    setup() {
        this.popup = useService("popup");
    }

    async onClick() {
        await this.popup.add(AdvanceOrdersPopup, {});
    }
}

ProductScreen.addControlButton({
    component: AdvanceOrdersButton,
    condition() {
        return true;
    },
});
