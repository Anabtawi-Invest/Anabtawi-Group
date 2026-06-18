import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        const linesToSend = this.currentOrder.payment_ids.filter(
            (pl) =>
                pl.payment_method_id?.use_payment_terminal === "apexecr" &&
                !pl.isDone() &&
                ["pending", "retry"].includes(pl.getPaymentStatus()) &&
                pl.amount > 0
        );
        if (linesToSend.length) {
            const oldAutoValidate = this.pos.config.auto_validate_terminal_payment;
            this.pos.config.auto_validate_terminal_payment = false;
            try {
                for (const line of linesToSend) {
                    await this.sendPaymentRequest(line);
                    if (!line.isDone()) {
                        return;
                    }
                }
            } finally {
                this.pos.config.auto_validate_terminal_payment = oldAutoValidate;
            }
        }
        return await super.validateOrder(isForceValidate);
    },
});

