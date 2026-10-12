/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation() {
        const ok = await super.askBeforeValidation(...arguments);
        if (ok === false) {
            return false;
        }

        const partner = this.order.getPartner();
        const customerAccountAmount = this.order.payment_ids
            .filter((line) => line.payment_method_id?.type === "pay_later" && line.amount > 0)
            .reduce((total, line) => total + line.amount, 0);
        if (!partner || customerAccountAmount <= 0) {
            return true;
        }

        let status;
        try {
            status = await this.pos.data.call("res.partner", "pos_check_employee_due_limit", [
                partner.id,
                this.pos.config.id,
                customerAccountAmount,
            ]);
        } catch {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Due Limit Check Failed"),
                body: _t(
                    "Could not verify the customer's due limit. Check the connection and try again."
                ),
            });
            return false;
        }

        if (status?.blocked) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Due Limit Exceeded"),
                body: status.message,
            });
            return false;
        }
        return true;
    },
});
