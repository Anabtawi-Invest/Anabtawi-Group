/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    onMounted() {
        super.onMounted();
        this._autoSuggestHospitalityPayment();
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

        const method = this.payment_methods_from_config.find(
            (paymentMethod) => paymentMethod.id === hospitalityPaymentMethod.id
        );
        if (method) {
            this.addNewPaymentLine(method);
        }
    },
});
