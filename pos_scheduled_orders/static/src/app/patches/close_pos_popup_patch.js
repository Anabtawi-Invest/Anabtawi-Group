/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

patch(ClosePosPopup.prototype, {
    setup() {
        super.setup(...arguments);
        // Auto-populate counted amount with expected amount by default to avoid 0 counted difference alerts
        if (this.state && this.state.payments) {
            if (this.props.default_cash_details && this.props.default_cash_details.id) {
                const cashId = this.props.default_cash_details.id;
                if (this.state.payments[cashId] && (!this.state.payments[cashId].counted || parseFloat(this.state.payments[cashId].counted) === 0)) {
                    this.state.payments[cashId].counted = this.props.default_cash_details.amount || 0;
                }
            }
            if (Array.isArray(this.props.non_cash_payment_methods)) {
                for (const pm of this.props.non_cash_payment_methods) {
                    if (this.state.payments[pm.id] && (!this.state.payments[pm.id].counted || parseFloat(this.state.payments[pm.id].counted) === 0)) {
                        this.state.payments[pm.id].counted = pm.amount || 0;
                    }
                }
            }
        }
    },

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
