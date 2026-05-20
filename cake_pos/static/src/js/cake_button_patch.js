/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { patch } from "@web/core/utils/patch";
import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/actionpad_widget/actionpad_widget";
import { CustomCakePopup } from "./cake_popup";

export class CakeButton extends Component {
    static template = "cake_pos.CakeButton";
    static props = {};

    setup() {
        this.popup = useService("popup");
        this.pos = usePos();
    }

    async openCakePopup() {
        await this.popup.add(CustomCakePopup, {});
    }
}

patch(ActionpadWidget, {
    components: {
        ...ActionpadWidget.components,
        CakeButton,
    },
});
