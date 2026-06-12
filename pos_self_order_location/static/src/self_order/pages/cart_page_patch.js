/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { useState, onMounted, onWillUnmount } from "@odoo/owl";
import { CartPage } from "@pos_self_order/app/pages/cart_page/cart_page";
import { _t } from "@web/core/l10n/translation";

patch(CartPage.prototype, {
    setup() {
        super.setup(...arguments);
        this.locationState = useState({
            loading: false,
            error: "",
        });
        this.cartStatusState = useState({ tick: 0 });
        const session = this.selfOrder.getCustomerSession?.();
        this.phoneState = useState({
            name: session?.name || "",
            phone: session?.phone || "",
            otpCode: "",
            otpSent: false,
            loading: false,
            error: "",
        });
        this._requestStateUnsubscribe = this.selfOrder.onRequestStateUpdate?.((orderAccessToken) => {
            if (orderAccessToken === this.selfOrder.currentOrder?.access_token) {
                this.cartStatusState.tick++;
            }
        });
        onMounted(() => {
            const order = this.selfOrder.currentOrder;
            if (order?.access_token && this.selfOrder.isOrderLockedForPayment?.(order)) {
                this.selfOrder.trackOrderRequest(order.access_token);
            }
        });
        onWillUnmount(() => {
            this._requestStateUnsubscribe?.();
        });
    },

    get requiresCustomerPhone() {
        return Boolean(this.selfOrder.requiresCustomerPhone?.());
    },

    get requiresPhoneOtp() {
        return Boolean(this.selfOrder.requiresPhoneOtp?.());
    },

    get hasVerifiedCustomer() {
        return Boolean(this.selfOrder.hasVerifiedCustomer?.());
    },

    get verifiedCustomerLabel() {
        const session = this.selfOrder.getCustomerSession?.();
        if (!session) {
            return "";
        }
        return session.name ? `${session.name} (${session.phone})` : session.phone;
    },

    async sendCustomerOtp() {
        if (!this.phoneState.phone?.trim()) {
            this.phoneState.error = _t("Please enter your phone number.");
            return;
        }
        this.phoneState.loading = true;
        this.phoneState.error = "";
        try {
            const result = await this.selfOrder.sendCustomerOtp(
                this.phoneState.phone.trim(),
                this.phoneState.name.trim() || null
            );
            this.phoneState.otpSent = true;
            if (result?.debug_otp) {
                this.phoneState.otpCode = result.debug_otp;
                this.selfOrder.notification.add(_t("Debug OTP: %s", result.debug_otp), {
                    type: "info",
                });
            }
            this.selfOrder.notification.add(_t("Verification code sent."), { type: "success" });
        } catch (error) {
            this.phoneState.error = error?.message || _t("Could not send verification code.");
        } finally {
            this.phoneState.loading = false;
        }
    },

    async verifyCustomerOtp() {
        if (!this.phoneState.otpCode?.trim()) {
            this.phoneState.error = _t("Please enter the verification code.");
            return;
        }
        this.phoneState.loading = true;
        this.phoneState.error = "";
        try {
            await this.selfOrder.verifyCustomerOtp(
                this.phoneState.phone.trim(),
                this.phoneState.otpCode.trim(),
                this.phoneState.name.trim() || null
            );
            this.cartStatusState.tick++;
        } catch (error) {
            this.phoneState.error = error?.message || _t("Invalid verification code.");
        } finally {
            this.phoneState.loading = false;
        }
    },

    async identifyCustomerByPhone() {
        if (!this.phoneState.phone?.trim()) {
            this.phoneState.error = _t("Please enter your phone number.");
            return;
        }
        this.phoneState.loading = true;
        this.phoneState.error = "";
        try {
            await this.selfOrder.identifyCustomer(
                this.phoneState.phone.trim(),
                this.phoneState.name.trim() || null
            );
            this.cartStatusState.tick++;
        } catch (error) {
            this.phoneState.error = error?.message || _t("Could not save phone number.");
        } finally {
            this.phoneState.loading = false;
        }
    },

    changeCustomerPhone() {
        this.selfOrder.clearCustomerSession();
        this.phoneState.otpSent = false;
        this.phoneState.otpCode = "";
        this.phoneState.error = "";
        this.cartStatusState.tick++;
    },

    get requiresCustomerLocation() {
        return this.selfOrder.config.self_ordering_mode === "mobile";
    },

    get requiresPaymentChoice() {
        return Boolean(this.selfOrder.usesPaymentChoice?.());
    },

    get isOrderLocked() {
        this.cartStatusState.tick;
        return Boolean(this.selfOrder.isOrderLockedForPayment?.());
    },

    get showOrderStatusBanner() {
        return this.isOrderLocked;
    },

    get orderStatusTitle() {
        const status = this.selfOrder.getOrderRequestStatus(
            this.selfOrder.currentOrder?.access_token
        );
        if (["accepted", "done"].includes(status.state)) {
            return _t("Your order has been confirmed!");
        }
        if (status.state === "cancelled") {
            return _t("Order cancelled");
        }
        return _t("Order submitted");
    },

    get orderStatusMessage() {
        const status = this.selfOrder.getOrderRequestStatus(
            this.selfOrder.currentOrder?.access_token
        );
        if (["accepted", "done"].includes(status.state)) {
            return _t("This order is already confirmed. You cannot place it again.");
        }
        if (status.state === "new" || !status.state) {
            return _t("This order is waiting for confirmation. You cannot pay again.");
        }
        return _t("This order has already been placed.");
    },

    get orderStatusAlertClass() {
        const status = this.selfOrder.getOrderRequestStatus(
            this.selfOrder.currentOrder?.access_token
        );
        if (["accepted", "done"].includes(status.state)) {
            return "alert-success";
        }
        return "alert-info";
    },

    get hasOnlinePaymentConfigured() {
        return Boolean(this.selfOrder.config.self_order_online_payment_method_id);
    },

    get showCashOnDeliveryOption() {
        return (
            !this.isOrderLocked &&
            this.requiresPaymentChoice &&
            this.selfOrder.config.self_order_allow_cash_on_delivery
        );
    },

    get showOnlineCardOption() {
        return (
            !this.isOrderLocked &&
            this.requiresPaymentChoice &&
            this.selfOrder.config.self_order_allow_online_card &&
            this.hasOnlinePaymentConfigured
        );
    },

    get showOnlineCardUnavailableHint() {
        return (
            !this.isOrderLocked &&
            this.requiresPaymentChoice &&
            this.selfOrder.config.self_order_allow_online_card &&
            !this.hasOnlinePaymentConfigured
        );
    },

    get hasAnyPaymentOption() {
        return this.showCashOnDeliveryOption || this.showOnlineCardOption;
    },

    get hasCustomerLocation() {
        const order = this.selfOrder.currentOrder;
        return Boolean(
            order?.customer_location_captured &&
                order.customer_latitude &&
                order.customer_longitude
        );
    },

    get hasPaymentPreference() {
        const order = this.selfOrder.currentOrder;
        return Boolean(order?.customer_payment_preference);
    },

    get selectedPaymentPreference() {
        return this.selfOrder.currentOrder?.customer_payment_preference || false;
    },

    get locationButtonLabel() {
        if (this.locationState.loading) {
            return _t("Getting location...");
        }
        if (this.hasCustomerLocation) {
            return _t("Location shared");
        }
        return _t("Share my location");
    },

    selectPaymentPreference(preference) {
        if (this.isOrderLocked) {
            return;
        }
        const order = this.selfOrder.currentOrder;
        if (!order) {
            return;
        }
        order.customer_payment_preference = preference;
    },

    async captureCustomerLocation() {
        if (this.isOrderLocked || !this.requiresCustomerLocation || this.locationState.loading) {
            return;
        }
        if (!navigator.geolocation) {
            this.locationState.error = _t("Location is not supported on this device.");
            this.selfOrder.notification.add(this.locationState.error, { type: "danger" });
            return;
        }

        this.locationState.loading = true;
        this.locationState.error = "";

        try {
            const position = await new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(resolve, reject, {
                    enableHighAccuracy: true,
                    timeout: 15000,
                    maximumAge: 0,
                });
            });
            const order = this.selfOrder.currentOrder;
            order.customer_latitude = position.coords.latitude;
            order.customer_longitude = position.coords.longitude;
            order.customer_location_captured = true;
            this.selfOrder.notification.add(_t("Location shared successfully."), {
                type: "success",
            });
        } catch (error) {
            this.locationState.error =
                error.code === 1
                    ? _t("Location permission denied. Please allow location access to continue.")
                    : _t("Could not get your location. Please try again.");
            this.selfOrder.notification.add(this.locationState.error, { type: "danger" });
        } finally {
            this.locationState.loading = false;
        }
    },

    async pay() {
        const order = this.selfOrder.currentOrder;
        if (this.selfOrder.isOrderLockedForPayment?.(order)) {
            this.selfOrder.confirmationPage(
                "order",
                this.selfOrder.config.self_ordering_mode,
                order.access_token
            );
            return;
        }
        if (this.requiresCustomerPhone && !this.hasVerifiedCustomer) {
            this.selfOrder.notification.add(
                _t("Please verify your phone number before placing the order."),
                { type: "warning" }
            );
            return;
        }
        if (this.requiresCustomerLocation && !this.hasCustomerLocation) {
            this.selfOrder.notification.add(
                _t("Please share your location before placing the order."),
                { type: "warning" }
            );
            return;
        }
        if (this.requiresPaymentChoice && !this.hasPaymentPreference) {
            this.selfOrder.notification.add(
                _t("Please choose how you want to pay."),
                { type: "warning" }
            );
            return;
        }
        return super.pay(...arguments);
    },
});
