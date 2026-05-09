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
        return formatCurrency(amount || 0, this.data.currencyId);
    }

    get paymentMethodLabel() {
        if (this.data.paymentMethod) {
            return this.data.paymentMethod;
        }
        return _t("N/A");
    }
}
