/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { formatCurrency } from "@web/core/currency";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";

patch(OrderReceipt.prototype, {
    get showPromotionalDiscountNote() {
        const order = this.order;
        return Boolean(
            order?.pricelist_id?.cap_enabled && toNumber(order.promotional_discount_amount) > 0
        );
    },

    get promotionalDiscountNote() {
        const amount = formatCurrency(
            toNumber(this.order.promotional_discount_amount),
            this.order.currency.id
        );
        return _t("Promotional Discount Applied: %s", amount);
    },

    get hideStandardDiscountSummary() {
        return Boolean(this.order?.pricelist_id?.cap_enabled);
    },
});

function toNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
}
