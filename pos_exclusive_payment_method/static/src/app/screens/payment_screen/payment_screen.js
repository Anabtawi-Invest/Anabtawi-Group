/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        const existingExclusiveLine = this.paymentLines.find(
            (paymentLine) =>
                paymentLine.payment_method_id.exclusive_payment_method &&
                paymentLine.payment_method_id.id !== paymentMethod.id
        );
        const hasDifferentSelectedMethod = this.paymentLines.some(
            (paymentLine) => paymentLine.payment_method_id.id !== paymentMethod.id
        );
        const hasExclusiveMethodInExistingLines = Boolean(existingExclusiveLine);

        if (
            (paymentMethod.exclusive_payment_method && hasDifferentSelectedMethod) ||
            hasExclusiveMethodInExistingLines
        ) {
            const blockingPaymentMethodName =
                paymentMethod.exclusive_payment_method && hasDifferentSelectedMethod
                    ? paymentMethod.name
                    : existingExclusiveLine?.payment_method_id?.name || paymentMethod.name;
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: `طريقة الدفع (${blockingPaymentMethodName}) لا يمكنك اختيار طريقة دفع أخرى معها`,
            });
            return false;
        }

        return await super.addNewPaymentLine(paymentMethod);
    },
});
