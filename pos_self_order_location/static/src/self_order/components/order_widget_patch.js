/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { OrderWidget } from "@pos_self_order/app/components/order_widget/order_widget";

patch(OrderWidget.prototype, {
    get buttonToShow() {
        const button = super.buttonToShow;
        const requiresLocation =
            this.selfOrder.config.self_ordering_mode === "mobile" &&
            this.router.activeSlot === "cart";
        const hasLocation = Boolean(
            this.selfOrder.currentOrder?.customer_location_captured &&
                this.selfOrder.currentOrder?.customer_latitude &&
                this.selfOrder.currentOrder?.customer_longitude
        );
        if (requiresLocation && !hasLocation) {
            return { ...button, disabled: true };
        }
        return button;
    },
});
