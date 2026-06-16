/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";

function toId(value) {
    if (!value) {
        return null;
    }
    if (typeof value === "number") {
        return value;
    }
    if (Array.isArray(value)) {
        return value[0] || null;
    }
    if (typeof value === "object") {
        return value.id || null;
    }
    if (typeof value === "string" && !Number.isNaN(Number(value))) {
        return Number(value);
    }
    return null;
}

patch(OrderReceipt.prototype, {
    get giftLines() {
        return this.order.lines?.filter((line) => line.is_gift) || [];
    },

    get hasGiftLines() {
        return this.giftLines.length > 0;
    },

    get hospitalityPaymentMethodId() {
        const rawHospitality = this.order.config.hospitality_payment_method_id;
        const hospitalityId = toId(rawHospitality);
        console.warn("[POS_HOSPITALITY_GIFT][RECEIPT] Hospitality method resolve", {
            rawHospitality,
            hospitalityId,
            configId: this.order.config?.id,
            orderName: this.order?.name,
        });
        return hospitalityId;
    },

    get customerPaidAmount() {
        const hospitalityPaymentMethodId = this.hospitalityPaymentMethodId;
        const paymentDebug = (this.paymentLines || []).map((line) => ({
            lineId: line.id,
            amount: line.getAmount?.() ?? line.amount,
            rawPaymentMethod: line.payment_method_id,
            paymentMethodId: toId(line.payment_method_id),
            paymentMethodName: line.payment_method_id?.name,
        }));
        console.warn("[POS_HOSPITALITY_GIFT][RECEIPT] Payment lines debug", {
            hospitalityPaymentMethodId,
            paymentDebug,
            orderAmountTotal: this.order.amount_total,
        });
        if (!hospitalityPaymentMethodId) {
            const fallbackAmount = this.paymentLines.reduce((sum, line) => sum + line.getAmount(), 0);
            console.warn("[POS_HOSPITALITY_GIFT][RECEIPT] Hospitality ID missing, using fallback", {
                fallbackAmount,
            });
            return fallbackAmount;
        }
        const computed = this.paymentLines.reduce((sum, line) => {
            if (toId(line.payment_method_id) === hospitalityPaymentMethodId) {
                return sum;
            }
            return sum + line.getAmount();
        }, 0);
        console.warn("[POS_HOSPITALITY_GIFT][RECEIPT] Computed customerPaidAmount", {
            computed,
        });
        return computed;
    },

    get companySponsoredAmount() {
        return Math.max(0, this.order.amount_total - this.customerPaidAmount);
    },
});
