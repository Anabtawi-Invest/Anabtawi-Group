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
        confirmLabel: { type: String, optional: true },
        cancelLabel: { type: String, optional: true },
        defaultAmount: { type: Number, optional: true },
        maxAmount: { type: Number, optional: true },
        maxLabel: { type: String, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Delivery Amount"),
        fieldLabel: _t("Delivery Amount"),
        confirmLabel: _t("Confirm"),
        cancelLabel: _t("Cancel"),
        defaultAmount: 0,
        maxLabel: _t("Counted Cash Balance"),
    };

    setup() {
        this.state = useState({
            deliveryAmount: this.env.utils.formatCurrency(this.props.defaultAmount, false),
        });
    }

    canConfirm() {
        return this.env.utils.isValidFloat(this.state.deliveryAmount);
    }

    confirm() {
        this.props.getPayload(this.env.utils.parseValidFloat(this.state.deliveryAmount));
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
