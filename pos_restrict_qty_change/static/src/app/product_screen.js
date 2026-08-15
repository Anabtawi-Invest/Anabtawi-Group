/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

patch(ProductScreen.prototype, {
    getNumpadButtons() {
        const buttons = super.getNumpadButtons();
        const order = this.currentOrder;
        const line = order?.getSelectedOrderline?.();
        if (
            !line ||
            this.pos.numpadMode !== "quantity" ||
            !this.pos.isPosQtyChangeRestricted(line, order)
        ) {
            return buttons;
        }
        return buttons.map((button) => {
            if (["quantity", "discount", "price", "Backspace"].includes(button.value)) {
                return button;
            }
            return { ...button, disabled: true };
        });
    },
});
