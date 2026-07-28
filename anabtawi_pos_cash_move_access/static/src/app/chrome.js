import { Chrome } from "@point_of_sale/app/pos_app";
import { patch } from "@web/core/utils/patch";

patch(Chrome.prototype, {
    get showCashMoveButton() {
        return this.pos.showCashMoveButton;
    },
});
