/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

const EXCLUSIVE_PAYMENT_METHOD_MESSAGE = "هذه البيمنت مثود لا يمكنك اختيار بيمنت مثود أخرى معها";

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        const hasDifferentSelectedMethod = this.paymentLines.some(
            (paymentLine) => paymentLine.payment_method_id.id !== paymentMethod.id
        );
        const hasExclusiveMethodInExistingLines = this.paymentLines.some(
            (paymentLine) =>
                paymentLine.payment_method_id.exclusive_payment_method &&
                paymentLine.payment_method_id.id !== paymentMethod.id
        );

        if (
            (paymentMethod.exclusive_payment_method && hasDifferentSelectedMethod) ||
            hasExclusiveMethodInExistingLines
        ) {
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: EXCLUSIVE_PAYMENT_METHOD_MESSAGE,
            });
            return false;
        }

        return await super.addNewPaymentLine(paymentMethod);
    },
});
