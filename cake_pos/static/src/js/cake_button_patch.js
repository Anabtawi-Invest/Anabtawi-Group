/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { useService } from "@web/core/utils/hooks";
import { CustomCakePopup } from "./cake_popup";

/**
 * Patch ProductScreen to add the "🎂 جاتو مخصص" button.
 * The button appears in the action-pad control buttons area.
 */
patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.popup = useService("popup");
    },

    async openCustomCakePopup() {
        const { confirmed } = await this.popup.add(CustomCakePopup, {});
        // confirmed == true means the item was added to the cart
    },
});
