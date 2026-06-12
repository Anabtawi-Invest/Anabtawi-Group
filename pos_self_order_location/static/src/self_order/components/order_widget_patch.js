/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { OrderWidget } from "@pos_self_order/app/components/order_widget/order_widget";
import { _t } from "@web/core/l10n/translation";

patch(OrderWidget.prototype, {
    get buttonToShow() {
        const button = super.buttonToShow;
        const isMobileCart =
            this.selfOrder.config.self_ordering_mode === "mobile" &&
            this.router.activeSlot === "cart";
        if (!isMobileCart) {
            return button;
        }

        const order = this.selfOrder.currentOrder;
        if (this.selfOrder.isOrderLockedForPayment?.(order)) {
            return { label: _t("View order status"), disabled: false };
        }

        const hasLocation = Boolean(
            order?.customer_location_captured &&
                order?.customer_latitude &&
                order?.customer_longitude
        );
        const requiresPaymentChoice = Boolean(this.selfOrder.usesPaymentChoice?.());
        const hasPaymentPreference = Boolean(order?.customer_payment_preference);
        const hasAnyPaymentOption =
            (requiresPaymentChoice &&
                (this.selfOrder.config.self_order_allow_cash_on_delivery ||
                    (this.selfOrder.config.self_order_allow_online_card &&
                        this.selfOrder.config.self_order_online_payment_method_id))) ||
            !requiresPaymentChoice;

        const hasVerifiedCustomer =
            !this.selfOrder.requiresCustomerPhone?.() ||
            this.selfOrder.hasVerifiedCustomer?.();

        if (
            !hasLocation ||
            !hasVerifiedCustomer ||
            !hasAnyPaymentOption ||
            (requiresPaymentChoice && !hasPaymentPreference)
        ) {
            return { ...button, disabled: true };
        }
        return button;
    },
});
