/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { LandingPage } from "@pos_self_order/app/pages/landing_page/landing_page";

patch(LandingPage.prototype, {
    get draftOrder() {
        const orders = this.selfOrder.models["pos.order"].filter(
            (order) => order.access_token && order.state === "draft"
        );
        if (!this.selfOrder.usesPaymentChoice?.()) {
            return orders;
        }
        return orders.filter(
            (order) =>
                order.access_token &&
                order.state === "draft" &&
                !this.selfOrder.isOrderLockedForPayment(order)
        );
    },

    clickMyOrder() {
        if (this.selfOrder.usesPaymentChoice?.()) {
            this.router.navigate("orderHistory");
            return;
        }
        this.router.navigate(this.draftOrder.length > 0 ? "cart" : "orderHistory");
    },
});
