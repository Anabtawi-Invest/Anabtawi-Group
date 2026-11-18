/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { getAdvanceEligiblePaymentMethods } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/advance_order_form_popup";

export class CakeAdvancePaymentPopup extends Component {
    static template = "pos_custom_cake.CakeAdvancePaymentPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        pos: Object,
        cakeTotal: Number,
        partnerName: { type: String, optional: true },
    };

    setup() {
        this.notification = useService("notification");
        const paymentMethods = getAdvanceEligiblePaymentMethods(this.props.pos);
        const defaultPmId = paymentMethods.length ? paymentMethods[0].id : null;
        this.state = useState({
            advance_amount_str: "",
            amount_tendered_str: "",
            selected_payment_method_id: defaultPmId,
            payment_methods: paymentMethods,
        });
    }

    get dialogTitle() {
        return _t("Cake Advance Payment");
    }

    get labels() {
        return {
            cakeTotal: _t("Cake Total"),
            advanceAmount: _t("Advance Amount"),
            amountTendered: _t("Amount Tendered"),
            amountTenderedHint: _t(
                "Customer paid amount at the register. Change is returned; only the advance is recorded."
            ),
            paymentMethod: _t("Payment method"),
            changeReturned: _t("Return to customer"),
            remaining: _t("Remaining after advance"),
            cancel: _t("Cancel"),
            confirm: _t("Confirm Advance"),
            customer: _t("Customer"),
        };
    }

    _parseAmount(value) {
        const normalized = String(value ?? "")
            .trim()
            .replace(",", ".");
        if (!normalized) {
            return 0;
        }
        const parsed = parseFloat(normalized);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    get advanceAmount() {
        return this._parseAmount(this.state.advance_amount_str);
    }

    get amountTendered() {
        return this._parseAmount(this.state.amount_tendered_str);
    }

    get cakeTotal() {
        return Number(this.props.cakeTotal || 0);
    }

    get remainingAfterAdvance() {
        return Math.max(this.cakeTotal - this.advanceAmount, 0);
    }

    get changeDue() {
        return Math.max(this.amountTendered - this.advanceAmount, 0);
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

    onAdvanceAmountInput(ev) {
        this.state.advance_amount_str = ev.target.value;
    }

    onAmountTenderedInput(ev) {
        this.state.amount_tendered_str = ev.target.value;
    }

    onAdvanceAmountBlur() {
        const advance = this.advanceAmount;
        if (advance > 0) {
            this.state.advance_amount_str = String(advance);
        }
        const tendered = this.amountTendered;
        if (tendered > 0 && tendered < advance) {
            this.state.amount_tendered_str = String(advance);
        }
    }

    onAmountTenderedBlur() {
        const tendered = this.amountTendered;
        if (tendered > 0) {
            this.state.amount_tendered_str = String(tendered);
        }
    }

    get noEligiblePaymentMethodsText() {
        return _t(
            "No eligible payment methods on this POS. Add manual cash or bank methods without terminal or QR integration in the Point of Sale configuration."
        );
    }

    confirm() {
        const advance = this.advanceAmount;
        const tendered = this.amountTendered;
        const total = this.cakeTotal;
        if (!advance || advance <= 0) {
            this.notification.add(_t("Advance amount must be greater than zero."), {
                type: "warning",
            });
            return;
        }
        if (advance >= total) {
            this.notification.add(
                _t("Advance amount must be less than the cake total. Use Confirm to pay in full."),
                { type: "warning" }
            );
            return;
        }
        if (!this.state.selected_payment_method_id) {
            this.notification.add(_t("Please select a payment method."), { type: "warning" });
            return;
        }
        if (tendered < advance) {
            this.notification.add(
                _t("Amount tendered cannot be less than the advance amount."),
                { type: "warning" }
            );
            return;
        }
        const tenderedFinal = tendered >= advance ? tendered : advance;
        const selectedPm = this.state.payment_methods.find(
            (pm) => pm.id === this.state.selected_payment_method_id
        );
        this.props.getPayload({
            advance_amount: advance,
            amount_tendered: tenderedFinal,
            payment_method_id: this.state.selected_payment_method_id,
            payment_method_name: selectedPm?.name || "",
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
