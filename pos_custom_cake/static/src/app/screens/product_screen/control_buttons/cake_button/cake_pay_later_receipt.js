/** @odoo-module **/

import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { formatCurrency } from "@web/core/currency";

export class CakePayLaterReceipt extends Component {
    static template = "pos_custom_cake.CakePayLaterReceipt";
    static props = {
        receipt: Object,
    };

    formatCurrency(amount) {
        return formatCurrency(amount || 0, this.props.receipt.currencyId);
    }

    get statusLabel() {
        return _t("Waiting for Payment");
    }
}
