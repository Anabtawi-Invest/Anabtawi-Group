/** @odoo-module **/

import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class DeliveryAmountReceipt extends Component {
    static template = "pos_delivery_amount.DeliveryAmountReceipt";
    static props = {
        title: String,
        companyName: String,
        posName: String,
        cashier: { type: String, optional: true },
        formattedAmount: String,
        date: String,
        moveName: { type: String, optional: true },
    };

    get labels() {
        return {
            amount: _t("AMOUNT"),
            cashier: _t("CASHIER"),
            journal: _t("JOURNAL"),
        };
    }
}
