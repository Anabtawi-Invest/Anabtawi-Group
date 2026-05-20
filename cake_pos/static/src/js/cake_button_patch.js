/** @odoo-module **/

/**
 * Patch ProductScreen to add the Custom Cake button.
 *
 * [J6] Odoo 17+ uses patch(Class, mixin) NOT patch(Class.prototype, mixin)
 */

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { useService } from "@web/core/utils/hooks";
import { CustomCakePopup } from "./cake_popup";

patch(ProductScreen, {
    async openCustomCakePopup() {
        await this.popup.add(CustomCakePopup, {});  // this.popup already exists
    },
});
