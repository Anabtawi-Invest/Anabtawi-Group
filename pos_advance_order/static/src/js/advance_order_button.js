/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

/**
 * Adds a handler used by the template extension to open the advance order screen.
 */
patch(ControlButtons.prototype, {
    onClickAdvanceOrder() {
        this.pos.showScreen("AdvanceOrderScreen");
    },
});
