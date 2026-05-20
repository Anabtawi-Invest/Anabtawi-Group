/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/actionpad_widget/actionpad_widget";
import { CustomCakePopup } from "./cake_popup";

patch(ActionpadWidget, {
    async openCustomCakePopup() {
        await this.popup.add(CustomCakePopup, {});
    },
});
