/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

export class MixedPaymentPopup extends Component {
    static template = "pos_advance.MixedPaymentPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        confirm: { type: Function, optional: true },
        getPayload: { type: Function, optional: true },
        totalAmount: Number,
    };

    setup() {
        this.pos = usePos();
        this.notification = useService("notification");
        
        this.state = useState({
            cashAmount: 0,
            cardAmount: 0,
        });
    }

    get totalPaid() {
        return parseFloat(this.state.cashAmount) + parseFloat(this.state.cardAmount);
    }

    get remaining() {
        return this.props.totalAmount - this.totalPaid;
    }

    onCashAmountChange(ev) {
        const value = parseFloat(ev.target.value) || 0;
        this.state.cashAmount = value;
        
        // Auto-calculate card amount if cash exceeds total
        if (value > this.props.totalAmount) {
            this.state.cashAmount = this.props.totalAmount;
            this.state.cardAmount = 0;
        } else if (this.totalPaid > this.props.totalAmount) {
            this.state.cardAmount = Math.max(0, this.props.totalAmount - value);
        }
    }

    onCardAmountChange(ev) {
        const value = parseFloat(ev.target.value) || 0;
        this.state.cardAmount = value;
        
        // Auto-calculate cash amount if card exceeds total
        if (value > this.props.totalAmount) {
            this.state.cardAmount = this.props.totalAmount;
            this.state.cashAmount = 0;
        } else if (this.totalPaid > this.props.totalAmount) {
            this.state.cashAmount = Math.max(0, this.props.totalAmount - value);
        }
    }

    setFullCash() {
        this.state.cashAmount = this.props.totalAmount;
        this.state.cardAmount = 0;
    }

    setFullCard() {
        this.state.cardAmount = this.props.totalAmount;
        this.state.cashAmount = 0;
    }

    onConfirm() {
        const cashAmount = parseFloat(this.state.cashAmount) || 0;
        const cardAmount = parseFloat(this.state.cardAmount) || 0;
        const totalPaid = cashAmount + cardAmount;

        if (totalPaid <= 0) {
            this.notification.add(
                _t("Please enter at least one payment amount."),
                { type: "warning" }
            );
            return;
        }

        if (totalPaid > this.props.totalAmount) {
            this.notification.add(
                _t("Total payment amount cannot exceed total expected amount."),
                { type: "warning" }
            );
            return;
        }

        const paymentData = {
            cash_amount: cashAmount,
            card_amount: cardAmount,
            amount_paid: totalPaid,
        };

        // Support both getPayload (from makeAwaitable) and confirm (direct usage)
        if (this.props.getPayload) {
            this.props.getPayload(paymentData);
        } else if (this.props.confirm) {
            this.props.confirm(paymentData);
        }
        
        this.props.close();
    }

    onCancel() {
        this.props.close();
    }
}
