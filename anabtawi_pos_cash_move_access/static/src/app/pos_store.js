/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    get showCashMoveButton() {
        if (!this.config.cash_control) {
            return false;
        }
        if (this.config._has_cash_move_perm) {
            return true;
        }
        const cashier = this.getCashier?.();
        if (cashier?.raw?._has_cash_move_perm) {
            return true;
        }
        return false;
    },
});
