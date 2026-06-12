/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { useState, onWillUnmount } from "@odoo/owl";
import { ConfirmationPage } from "@pos_self_order/app/pages/confirmation_page/confirmation_page";
import { _t } from "@web/core/l10n/translation";

const TRACKED_REQUEST_STATES = new Set(["new", "accepted", "done", "cancelled"]);
const CONFIRMATION_STATUS_POLL_MS = 3000;

patch(ConfirmationPage.prototype, {
    setup() {
        super.setup(...arguments);
        this.requestTrackingState = useState({ state: false });
        this._requestStateUnsubscribe = this.selfOrder.onRequestStateUpdate(
            (orderAccessToken, state) => {
                if (orderAccessToken === this.props.orderAccessToken) {
                    this.applyRequestState(state);
                }
            }
        );
        onWillUnmount(() => {
            this._requestStateUnsubscribe?.();
            clearInterval(this._requestStatusPoll);
        });
    },

    get tracksRequestStatus() {
        return Boolean(
            this.selfOrder.usesPaymentChoice?.() && this.props.orderAccessToken
        );
    },

    get requestState() {
        const serviceStatus = this.selfOrder.getOrderRequestStatus(
            this.props.orderAccessToken
        );
        if (serviceStatus?.loaded && serviceStatus.state) {
            return serviceStatus.state;
        }
        return this.requestTrackingState.state;
    },

    get showSubmittedMessage() {
        return (
            this.tracksRequestStatus &&
            (!this.requestState || this.requestState === "new")
        );
    },

    get showConfirmedMessage() {
        return (
            this.tracksRequestStatus &&
            ["accepted", "done"].includes(this.requestState)
        );
    },

    get showCancelledMessage() {
        return this.tracksRequestStatus && this.requestState === "cancelled";
    },

    get confirmationTitle() {
        if (this.showSubmittedMessage) {
            return _t("Order submitted successfully");
        }
        if (this.showConfirmedMessage) {
            return _t("Your order has been confirmed!");
        }
        if (this.showCancelledMessage) {
            return _t("Order cancelled");
        }
        return _t("We're preparing your order!");
    },

    get confirmationSubtitle() {
        if (this.showSubmittedMessage) {
            return _t("Please wait until your order is confirmed by our team.");
        }
        if (this.showConfirmedMessage) {
            return _t("We're preparing your order now.");
        }
        if (this.showCancelledMessage) {
            return _t("Please contact the store if you need help.");
        }
        return "";
    },

    get confirmationStatusAlertClass() {
        if (this.showConfirmedMessage) {
            return "alert-success";
        }
        if (this.showCancelledMessage) {
            return "alert-warning";
        }
        return "alert-info";
    },

    applyRequestState(state) {
        if (!TRACKED_REQUEST_STATES.has(state)) {
            return;
        }
        this.requestTrackingState.state = state;
    },

    async fetchRequestStatus() {
        if (!this.tracksRequestStatus || !this.props.orderAccessToken) {
            return;
        }
        await this.selfOrder.fetchOrderRequestStatus(this.props.orderAccessToken);
        const serviceStatus = this.selfOrder.getOrderRequestStatus(
            this.props.orderAccessToken
        );
        if (serviceStatus?.state) {
            this.applyRequestState(serviceStatus.state);
        }
    },

    startRequestStatusPolling() {
        if (!this.tracksRequestStatus) {
            return;
        }
        clearInterval(this._requestStatusPoll);
        this._requestStatusPoll = setInterval(
            () => this.fetchRequestStatus(),
            CONFIRMATION_STATUS_POLL_MS
        );
    },

    allowsUnpaidConfirmation(order) {
        return Boolean(
            order?.customer_payment_preference === "cash_on_delivery" ||
                (this.selfOrder.usesPaymentChoice?.() && order?.state === "draft")
        );
    },

    async initOrder(retry = true) {
        const order = this.selfOrder.models["pos.order"].find(
            (o) => o.access_token === this.props.orderAccessToken
        );

        if (!order && retry) {
            await this.selfOrder.getUserDataFromServer([this.props.orderAccessToken]);
            return this.initOrder(false);
        }

        this.selfOrder.selectedOrderUuid = order?.uuid;

        if (
            !order ||
            (!this.allowsUnpaidConfirmation(order) &&
                this.selfOrder.hasPaymentMethod() &&
                this.selfOrder.config.self_ordering_mode === "mobile" &&
                this.selfOrder.config.self_ordering_pay_after === "each" &&
                order.state !== "paid")
        ) {
            this.router.navigate("default");
            return;
        }

        this.selfOrder.selectedOrderUuid = order.uuid;
        this.selfOrder.trackOrderRequest(this.props.orderAccessToken);
        this.confirmedOrder.uiState.receiptReady = this.beforePrintOrder();
        this.state.onReload = false;

        await this.fetchRequestStatus();
        this.startRequestStatusPolling();
    },
});
