/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

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
    return null;
}

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        const added = await super.addNewPaymentLine(paymentMethod);
        if (!added) {
            return added;
        }
        if (!this._isHospitalityMethod(paymentMethod)) {
            return added;
        }
        const selectedLine = this.currentOrder.getSelectedPaymentline();
        if (!selectedLine) {
            return added;
        }
        const giftTotal = this._getGiftLinesTotalWithTax();
        if (giftTotal > 0) {
            selectedLine.setAmount(giftTotal);
            this.numberBuffer.set(giftTotal.toString());
        }
        return added;
    },

    onMounted() {
        super.onMounted();
        this._autoSuggestHospitalityPayment();
    },

    _isHospitalityMethod(paymentMethod) {
        const hospitalityMethodId = toId(this.pos?.config?.hospitality_payment_method_id);
        const methodId = toId(paymentMethod);
        if (hospitalityMethodId && methodId === hospitalityMethodId) {
            return true;
        }
        const methodName = (paymentMethod?.name || "").toLowerCase();
        return methodName.includes("hospitality");
    },

    _getGiftLinesTotalWithTax() {
        const lines = this.currentOrder?.lines || [];
        return lines.reduce((sum, line) => {
            if (!line.is_gift) {
                return sum;
            }
            return sum + (line.priceIncl ?? 0);
        }, 0);
    },

    _autoSuggestHospitalityPayment() {
        const order = this.currentOrder;
        const config = this.pos?.config;
        if (!order || !config?.auto_suggest_hospitality_payment) {
            return;
        }

        const hasGiftLine = order.lines?.some((line) => line.is_gift);
        const hospitalityPaymentMethod = config.hospitality_payment_method_id;
        if (!hasGiftLine || !hospitalityPaymentMethod || order.payment_ids.length) {
            return;
        }

        const hospitalityPaymentMethodId = toId(hospitalityPaymentMethod);
        const method = this.payment_methods_from_config.find(
            (paymentMethod) => toId(paymentMethod) === hospitalityPaymentMethodId
        );
        if (method) {
            this.addNewPaymentLine(method);
        }
    },
});
