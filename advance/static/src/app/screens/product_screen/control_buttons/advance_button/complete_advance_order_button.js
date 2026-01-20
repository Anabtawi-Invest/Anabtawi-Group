/** @odoo-module **/

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { AdvanceOrderListPopup } from "./advance_order_list_popup";

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.pos = this.env.services.pos;
    },

    onClickCompleteAdvanceOrder() {
    console.log("[ADVANCE] Complete Advance Order clicked");

    this.dialog.add(AdvanceOrderListPopup);

}
});
