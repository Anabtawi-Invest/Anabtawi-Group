/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { CartPage } from "@pos_self_order/app/pages/cart_page/cart_page";
import { _t } from "@web/core/l10n/translation";

patch(CartPage.prototype, {
    setup() {
        super.setup(...arguments);
        this.locationState = useState({
            loading: false,
            error: "",
        });
    },

    get requiresCustomerLocation() {
        return this.selfOrder.config.self_ordering_mode === "mobile";
    },

    get hasCustomerLocation() {
        const order = this.selfOrder.currentOrder;
        return Boolean(
            order?.customer_location_captured &&
                order.customer_latitude &&
                order.customer_longitude
        );
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

    async captureCustomerLocation() {
        if (!this.requiresCustomerLocation || this.locationState.loading) {
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
        if (this.requiresCustomerLocation && !this.hasCustomerLocation) {
            this.selfOrder.notification.add(
                _t("Please share your location before placing the order."),
                { type: "warning" }
            );
            return;
        }
        return super.pay(...arguments);
    },
});
