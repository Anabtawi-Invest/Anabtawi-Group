/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

patch(ClosePosPopup.prototype, {
    setCountedToExpected(paymentId, expectedAmount) {
        if (this.state && this.state.payments && this.state.payments[paymentId]) {
            this.state.payments[paymentId].counted = expectedAmount;
        }
    },
    onCountedAmountInput(paymentId, ev) {
        const val = parseFloat(ev.target.value || 0);
        if (this.state && this.state.payments && this.state.payments[paymentId]) {
            this.state.payments[paymentId].counted = isNaN(val) ? 0 : val;
        }
    },
});
