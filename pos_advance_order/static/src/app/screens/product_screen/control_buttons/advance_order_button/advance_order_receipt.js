/** @odoo-module **/

import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { formatCurrency } from "@web/core/currency";

export class AdvanceOrderReceipt extends Component {
    static template = "pos_advance_order.AdvanceOrderReceipt";
    static props = {
        receipt: Object,
    };

    get data() {
        return this.props.receipt;
    }

    formatCurrency(amount) {
        const value = amount || 0;
        if (this.data.currencyId) {
            return formatCurrency(value, this.data.currencyId);
        }
        return value.toFixed(2);
    }

    get paymentMethodLabel() {
        if (this.data.paymentMethod) {
            return this.data.paymentMethod;
        }
        return _t("N/A");
    }

    get hasDepositPaymentLines() {
        return !!(this.data.depositPaymentLines && this.data.depositPaymentLines.length);
    }

    get hasCompletionPaymentLines() {
        return !!(this.data.completionPaymentLines && this.data.completionPaymentLines.length);
    }

    formatPaymentLineAmount(amount) {
        return this.formatCurrency(amount || 0);
    }
}
