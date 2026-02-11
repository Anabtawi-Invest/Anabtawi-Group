/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

/* =====================================================
   1️⃣ Force payment amount = advance_amount
   ===================================================== */
patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        const order = this.currentOrder;

        const result = await super.addNewPaymentLine(paymentMethod);

        if (
            result &&
            order?.is_advance_order &&
            order.advance_amount
        ) {
            const line = this.selectedPaymentLine;

            if (line) {
                console.log("[ADVANCE] Forcing payment amount", order.advance_amount);

                // 🔥 Force payment to advance amount
                line.setAmount(order.advance_amount);
            }
        }

        return result;
    },
});

/* =====================================================
   2️⃣ Treat order as PAID when advance is paid
   ===================================================== */
patch(PosOrder.prototype, {
    isPaid() {
        if (this.is_advance_order && this.advance_amount) {
            const paid = this.payment_ids.reduce(
                (sum, p) => sum + (p.amount || 0),
                0
            );

            console.log("[ADVANCE] isPaid()", {
                paid,
                advance: this.advance_amount,
                ok: paid >= this.advance_amount,
            });

            return paid >= this.advance_amount;
        }

        return super.isPaid();
    },
});
