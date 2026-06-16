/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";

patch(OrderReceipt.prototype, {
    get giftLines() {
        return this.order.lines?.filter((line) => line.is_gift) || [];
    },

    get hasGiftLines() {
        return this.giftLines.length > 0;
    },

    get hospitalityPaymentMethodId() {
        return this.order.config.hospitality_payment_method_id?.id;
    },

    get customerPaidAmount() {
        const hospitalityPaymentMethodId = this.hospitalityPaymentMethodId;
        if (!hospitalityPaymentMethodId) {
            return this.paymentLines.reduce((sum, line) => sum + line.getAmount(), 0);
        }
        return this.paymentLines.reduce((sum, line) => {
            if (line.payment_method_id.id === hospitalityPaymentMethodId) {
                return sum;
            }
            return sum + line.getAmount();
        }, 0);
    },

    get companySponsoredAmount() {
        return Math.max(0, this.order.amount_total - this.customerPaidAmount);
    },
});
