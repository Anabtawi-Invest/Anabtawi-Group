import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.use_payment_terminal === "apexecr" && this.isRefundOrder) {
            const refundedOrder = this.currentOrder.lines[0]?.refunded_orderline_id?.order_id;
            if (!refundedOrder) {
                this.pos.notification.add(_t("No original order found to refund."), { type: "warning" });
                return false;
            }
            const alreadyUsedRefs = new Set(
                this.currentOrder.payment_ids.map((pl) => pl.uiState?.apexecr_parent_rrn).filter((x) => x)
            );
            const candidates = refundedOrder.payment_ids.filter(
                (pl) =>
                    pl.payment_method_id.use_payment_terminal === "apexecr" &&
                    (pl.apexecr_rrn || pl.apexecr_auth_code) &&
                    !alreadyUsedRefs.has(pl.apexecr_rrn)
            );
            const amountDue = Math.abs(this.currentOrder.remainingDue);
            const matched = candidates.find((pl) => pl.amount === amountDue) || candidates[0] || null;
            if (!matched) {
                this.pos.notification.add(
                    _t("No refundable ApexECR payment found (missing RRN/AuthCode in original payment)."),
                    { type: "warning" }
                );
                return false;
            }
            const res = await super.addNewPaymentLine(paymentMethod);
            if (!res) {
                return res;
            }
            const newLine = this.paymentLines.at(-1);
            const amountToSet = Math.min(Math.abs(newLine.amount), matched.amount);
            newLine.setAmount(-amountToSet);
            newLine.updateRefundPaymentLine(matched);
            return res;
        }
        return await super.addNewPaymentLine(paymentMethod);
    },
});

