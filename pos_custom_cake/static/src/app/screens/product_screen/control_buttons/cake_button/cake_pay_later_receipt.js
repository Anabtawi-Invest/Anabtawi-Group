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

    get labels() {
        return {
            customCakeOrder: _t("Custom Cake Order"),
            orderNumber: _t("Order Number"),
            date: _t("Date"),
            customer: _t("Customer"),
            status: _t("Status"),
            pieces: _t("Pieces"),
            total: _t("Total"),
            payAtCounter: _t("Please pay at the counter when ready."),
        };
    }
}
