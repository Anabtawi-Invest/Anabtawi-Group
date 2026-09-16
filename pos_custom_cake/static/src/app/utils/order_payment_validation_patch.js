/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { OrderPaymentValidation } from "@point_of_sale/app/utils/order_payment_validation";

patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation() {
        const order = this.order;
        if (order?.pos_cake_order_id && order.pos_cake_product_id && !order.hasLinkedCakeProduct()) {
            order.clearPosCakeOrderId();
            this.pos.dialog.add(AlertDialog, {
                title: _t("Custom Cake Link Cleared"),
                body: _t(
                    "This ticket was linked to a custom cake order, but the cake product is no longer on the ticket. The cake link was removed and the cake order was not marked as paid."
                ),
            });
        }
        return await super.askBeforeValidation(...arguments);
    },
});