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
        const rawConfigHospitality = this.order.config.hospitality_payment_method_id;
        const rawCompanyHospitality = this.order.company?.hospitality_payment_method_id;
        return toId(rawConfigHospitality) || toId(rawCompanyHospitality);
    },

    isHospitalityPaymentLine(line) {
        const paymentMethod = line?.payment_method_id || {};
        const paymentMethodId = toId(paymentMethod);
        const hospitalityPaymentMethodId = this.hospitalityPaymentMethodId;
        if (hospitalityPaymentMethodId && paymentMethodId === hospitalityPaymentMethodId) {
            return true;
        }

        if (
            paymentMethod.is_gift_payment_method === true ||
            paymentMethod.is_hospitality_payment_method === true
        ) {
            return true;
        }

        const paymentMethodName = (paymentMethod.name || "").trim().toLowerCase();
        return paymentMethodName === "hospitality" || paymentMethodName.includes("hospitality");
    },

    get customerPaidAmount() {
        return this.paymentLines.reduce((sum, line) => {
            if (this.isHospitalityPaymentLine(line)) {
                return sum;
            }
            return sum + line.getAmount();
        }, 0);
    },

    get companySponsoredAmount() {
        return Math.max(0, this.order.amount_total - this.customerPaidAmount);
    },
});
