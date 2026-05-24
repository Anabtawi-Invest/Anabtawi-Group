/** @odoo-module **/
// pos_delivery_amount/static/src/js/DeliveryAmountPopup.js

import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { _t } from "@web/core/l10n/translation";
import { useState } from "@odoo/owl";

/**
 * DeliveryAmountPopup
 *
 * Displayed as the last step before POS session closure.
 * Asks the cashier how much cash will be delivered to the bank.
 */
export class DeliveryAmountPopup extends AbstractAwaitablePopup {
    static template = "pos_delivery_amount.DeliveryAmountPopup";

    static defaultProps = {
        confirmText: _t("Confirm"),
        cancelText: _t("Cancel"),
        title: _t("Delivery Amount"),
        body: "",
    };

    setup() {
        super.setup();
        this.state = useState({
            deliveryAmount: "0",
            validationError: "",
        });
    }

    // ----------------------------------------------------------------
    // Getters
    // ----------------------------------------------------------------

    get parsedAmount() {
        const val = parseFloat(this.state.deliveryAmount);
        return isNaN(val) ? 0.0 : val;
    }

    // ----------------------------------------------------------------
    // Handlers
    // ----------------------------------------------------------------

    onAmountInput(ev) {
        this.state.deliveryAmount = ev.target.value;
        this.state.validationError = "";
    }

    /**
     * Validate locally before sending to server.
     * @returns {boolean}
     */
    _localValidate() {
        const amount = this.parsedAmount;

        if (amount < 0) {
            this.state.validationError = _t("Delivery Amount cannot be negative.");
            return false;
        }

        const cashBalance = this.props.cashBalance || 0;
        if (amount > cashBalance) {
            this.state.validationError = _t(
                "Delivery Amount cannot exceed counted cash balance."
            );
            return false;
        }

        return true;
    }

    async confirm() {
        if (!this._localValidate()) {
            return;
        }
        this.props.resolve({ confirmed: true, payload: this.parsedAmount });
        this.props.close();
    }

    cancel() {
        this.props.resolve({ confirmed: false, payload: null });
        this.props.close();
    }
}
