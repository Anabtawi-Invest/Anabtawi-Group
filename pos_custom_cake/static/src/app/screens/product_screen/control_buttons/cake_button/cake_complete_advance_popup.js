/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { getAdvanceEligiblePaymentMethods } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/advance_order_form_popup";

export class CakeCompleteAdvancePopup extends Component {
    static template = "pos_custom_cake.CakeCompleteAdvancePopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        pos: Object,
        order: Object,
    };

    setup() {
        this.notification = useService("notification");
        const paymentMethods = getAdvanceEligiblePaymentMethods(this.props.pos);
        const defaultPmId = paymentMethods.length ? paymentMethods[0].id : null;
        const remaining = Number(this.props.order?.amount_remaining || 0);
        this.state = useState({
            amount_tendered: remaining,
            selected_payment_method_id: defaultPmId,
            payment_methods: paymentMethods,
        });
    }

    get dialogTitle() {
        return _t("Complete Cake Advance");
    }

    get labels() {
        return {
            orderNumber: _t("Order Number"),
            customer: _t("Customer"),
            cakeTotal: _t("Cake Total"),
            advancePaid: _t("Advance Paid"),
            remaining: _t("Remaining"),
            amountTendered: _t("Amount Tendered"),
            amountTenderedHint: _t("Customer paid amount for remaining settlement."),
            paymentMethod: _t("Payment method"),
            changeReturned: _t("Change Returned"),
            cancel: _t("Cancel"),
            complete: _t("Complete Payment"),
        };
    }

    get remainingAmount() {
        return Number(this.props.order?.amount_remaining || 0);
    }

    get changeDue() {
        return Math.max(Number(this.state.amount_tendered || 0) - this.remainingAmount, 0);
    }

    formatAmount(amount) {
        return formatCurrency(amount || 0, this.props.pos.currency?.id);
    }

    paymentMethodIconSrc(pm) {
        if (!pm) {
            return "";
        }
        if (pm.image) {
            return `/web/image/pos.payment.method/${pm.id}/image`;
        }
        if (pm.type === "cash") {
            return "/point_of_sale/static/src/img/money.png";
        }
        return "/point_of_sale/static/src/img/card-bank.png";
    }

    isPaymentSelected(pm) {
        return pm.id === this.state.selected_payment_method_id;
    }

    paymentMethodRowClass(pm) {
        const selected = this.isPaymentSelected(pm);
        return `button paymentmethod btn btn-secondary btn-lg lh-lg d-flex justify-content-between align-items-center flex-fill text-start ${
            selected ? "border border-3 border-primary" : "opacity-75"
        }`;
    }

    selectPaymentMethod(pm) {
        this.state.selected_payment_method_id = pm.id;
    }

    onAmountTenderedInput(ev) {
        const value = Number(ev.target.value || 0);
        this.state.amount_tendered = Number.isFinite(value) ? value : 0;
    }

    get noEligiblePaymentMethodsText() {
        return _t(
            "No eligible payment methods on this POS. Add manual cash or bank methods without terminal or QR integration in the Point of Sale configuration."
        );
    }

    confirm() {
        if (!this.state.selected_payment_method_id) {
            this.notification.add(_t("Please select a payment method."), { type: "warning" });
            return;
        }
        if (this.state.amount_tendered < this.remainingAmount) {
            this.notification.add(
                _t("Amount tendered cannot be less than remaining amount."),
                { type: "warning" }
            );
            return;
        }
        const selectedPm = this.state.payment_methods.find(
            (pm) => pm.id === this.state.selected_payment_method_id
        );
        this.props.getPayload({
            order_id: this.props.order.id,
            payment_method_id: this.state.selected_payment_method_id,
            payment_method_name: selectedPm?.name || "",
            amount_tendered: this.state.amount_tendered,
            change_amount: this.changeDue,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
