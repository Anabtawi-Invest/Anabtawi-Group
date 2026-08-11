/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { Input } from "@point_of_sale/app/components/inputs/input/input";

export class DeliveryAmountPopup extends Component {
    static template = "pos_delivery_amount.DeliveryAmountPopup";
    static components = { Dialog, Input };
    static props = {
        title: { type: String, optional: true },
        fieldLabel: { type: String, optional: true },
        reasonLabel: { type: String, optional: true },
        confirmLabel: { type: String, optional: true },
        cancelLabel: { type: String, optional: true },
        defaultAmount: { type: Number, optional: true },
        maxAmount: { type: Number, optional: true },
        maxLabel: { type: String, optional: true },
        requireReason: { type: Boolean, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Cash Delivery"),
        fieldLabel: _t("Amount to be out"),
        reasonLabel: _t("Reason"),
        confirmLabel: _t("Confirm"),
        cancelLabel: _t("Cancel"),
        defaultAmount: 0,
        maxLabel: _t("Counted Cash Balance"),
        requireReason: false,
    };

    setup() {
        this.state = useState({
            deliveryAmount: this.env.utils.formatCurrency(this.props.defaultAmount, false),
            reason: "",
        });
    }

    get trimmedReason() {
        return (this.state.reason || "").trim();
    }

    canConfirm() {
        if (!this.env.utils.isValidFloat(this.state.deliveryAmount)) {
            return false;
        }
        if (this.props.requireReason && !this.trimmedReason) {
            return false;
        }
        return true;
    }

    confirm() {
        this.props.getPayload({
            amount: this.env.utils.parseValidFloat(this.state.deliveryAmount),
            reason: this.trimmedReason,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
