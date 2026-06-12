/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { OrdersHistoryPage } from "@pos_self_order/app/pages/order_history_page/order_history_page";
import { _t } from "@web/core/l10n/translation";

patch(OrdersHistoryPage.prototype, {
    setup() {
        super.setup(...arguments);
        this.historyState = useState({ loading: true, tick: 0 });
        this._requestStateUnsubscribe = this.selfOrder.onRequestStateUpdate?.(() => {
            this.historyState.tick++;
        });

        onWillStart(async () => {
            if (this.selfOrder.requiresCustomerPhone?.()) {
                if (!this.selfOrder.hasVerifiedCustomer?.()) {
                    this.historyState.loading = false;
                    return;
                }
                await this.selfOrder.refreshCustomerOrderHistory();
            } else if (this.selfOrder.usesPaymentChoice?.()) {
                await this.selfOrder.refreshCustomerOrderHistory();
            }
            this.historyState.loading = false;
        });

        onMounted(() => {
            if (!this.selfOrder.usesPaymentChoice?.()) {
                return;
            }
            this._historyStatusPoll = setInterval(() => {
                this.selfOrder.fetchAllOrderRequestStatuses();
            }, 5000);
        });

        onWillUnmount(() => {
            this._requestStateUnsubscribe?.();
            clearInterval(this._historyStatusPoll);
        });
    },

    get orders() {
        this.historyState.tick;
        return this.selfOrder.getHistoryOrders?.() || super.orders;
    },

    get needsPhoneVerification() {
        return (
            this.selfOrder.requiresCustomerPhone?.() &&
            !this.selfOrder.hasVerifiedCustomer?.()
        );
    },

    goToCartForPhoneVerification() {
        this.router.navigate("cart");
    },

    get activeCartOrder() {
        if (!this.selfOrder.usesPaymentChoice?.()) {
            return null;
        }
        return this.selfOrder.models["pos.order"].find(
            (order) =>
                order.access_token &&
                order.state === "draft" &&
                order.lines.length > 0 &&
                !this.selfOrder.isOrderLockedForPayment(order)
        );
    },

    openActiveCart() {
        if (!this.activeCartOrder) {
            return;
        }
        this.selfOrder.selectedOrderUuid = this.activeCartOrder.uuid;
        this.router.navigate("cart");
    },

    editOrder(order) {
        if (order.state === "draft" && !this.selfOrder.isOrderLockedForPayment?.(order)) {
            this.selfOrder.selectedOrderUuid = order.uuid;
            this.router.navigate("cart");
            return;
        }
        if (order.access_token) {
            this.selfOrder.confirmationPage(
                "order",
                this.selfOrder.config.self_ordering_mode,
                order.access_token
            );
        }
    },

    getOrderState(state, order = null) {
        if (!order) {
            return super.getOrderState(state);
        }
        if (order.state === "paid") {
            return _t("Paid");
        }
        if (this.selfOrder.isOrderLockedForPayment?.(order)) {
            const status = this.selfOrder.getOrderRequestStatus(order.access_token);
            if (["accepted", "done"].includes(status.state)) {
                return _t("Confirmed");
            }
            if (status.state === "cancelled") {
                return _t("Cancelled");
            }
            return _t("Submitted");
        }
        if (state === "draft") {
            return _t("In progress");
        }
        return super.getOrderState(state);
    },

    getOrderStateBadgeClass(order) {
        if (order.state === "paid") {
            return "text-bg-success";
        }
        const status = this.selfOrder.getOrderRequestStatus(order.access_token);
        if (["accepted", "done"].includes(status.state)) {
            return "text-bg-success";
        }
        if (status.state === "cancelled") {
            return "text-bg-warning";
        }
        if (this.selfOrder.isOrderLockedForPayment?.(order)) {
            return "text-bg-info";
        }
        if (order.state === "draft") {
            return "text-bg-primary";
        }
        return "text-bg-secondary";
    },

    getOrderStatusMessage(order) {
        if (order.state === "paid") {
            return _t("Payment received.");
        }
        const status = this.selfOrder.getOrderRequestStatus(order.access_token);
        if (["accepted", "done"].includes(status.state)) {
            return _t("Confirmed by the store. We're preparing your order.");
        }
        if (status.state === "cancelled") {
            return _t("This order was cancelled.");
        }
        if (this.selfOrder.isOrderLockedForPayment?.(order)) {
            return _t("Waiting for confirmation from the store.");
        }
        if (order.state === "draft") {
            return _t("Still in your cart.");
        }
        return "";
    },

    getPaymentPreferenceLabel(order) {
        if (order.customer_payment_preference === "cash_on_delivery") {
            return _t("Cash on delivery");
        }
        if (order.customer_payment_preference === "online_card") {
            return order.state === "paid" ? _t("Card (Paid)") : _t("Card (Unpaid)");
        }
        return "";
    },
});
