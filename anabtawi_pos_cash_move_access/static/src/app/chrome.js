import { Chrome } from "@point_of_sale/app/pos_app";
import { patch } from "@web/core/utils/patch";

patch(Chrome.prototype, {
    get showCashMoveButton() {
        // Keep standard cash-control and permission checks, without forcing manager role.
        return Boolean(this.pos.config.cash_control && this.pos.config._has_cash_move_perm);
    },
});
