/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosPayment } from "@point_of_sale/app/models/pos_payment";
import { MepsWaitingPopup } from "./meps_waiting_popup";

async function callMepsSale(paymentMethodId, amount, invoiceNumber, referenceNumber) {
    return rpc("/web/dataset/call_kw", {
        model: "pos.payment.method",
        method: "meps_sale",
        args: [[paymentMethodId], amount, invoiceNumber, referenceNumber],
        kwargs: {},
    });
}

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        const added = await super.addNewPaymentLine(paymentMethod);
        if (!added || !paymentMethod?.meps_enabled) {
            return added;
        }

        const paymentLine = this.currentOrder.getSelectedPaymentline() || this.paymentLines.at(-1);
        if (!paymentLine) {
            return added;
        }

        const amount = Math.abs(paymentLine.amount);
        const invoiceNumber = String(this.currentOrder.pos_reference || this.currentOrder.uuid || "").slice(-8);
        const referenceNumber = this.currentOrder.uuid || "";

        let closeWaiting = this.pos.dialog.add(MepsWaitingPopup, {
            body: _t("Please follow the instructions on the payment terminal..."),
        });

        let result;
        try {
            result = await callMepsSale(paymentMethod.id, amount, invoiceNumber, referenceNumber);
        } catch (error) {
            closeWaiting?.();
            closeWaiting = null;
            this.currentOrder.removePaymentline(paymentLine);
            this.numberBuffer.reset();
            this.pos.dialog.add(AlertDialog, {
                title: _t("MEPS Payment Error"),
                body: error?.data?.message || error?.message || _t("Could not reach the MEPS payment gateway."),
            });
            return false;
        }
        closeWaiting?.();
        closeWaiting = null;

        const approved = result?.WebResponseStatus === "Success" && result?.PosRespStatus === "1";
        if (!approved) {
            this.currentOrder.removePaymentline(paymentLine);
            this.numberBuffer.reset();
            this.pos.dialog.add(AlertDialog, {
                title: _t("MEPS Payment Declined"),
                body:
                    result?.WebResponseErrorDesc ||
                    result?.PosRespText ||
                    _t("The MEPS terminal declined the transaction."),
            });
            return false;
        }

        paymentLine.meps_rrn = result.PosRRN || false;
        paymentLine.meps_auth_code = result.PosAuthCode || false;
        paymentLine.meps_resp_code = result.PosRespCode || false;
        paymentLine.meps_resp_text = result.PosRespText || false;
        paymentLine.meps_card_pan = result.PosPan || false;
        paymentLine.meps_card_entry_mode = result.PosCardEntryModeId || false;
        paymentLine.meps_batch_number = result.PosBatchNumber || false;
        paymentLine.meps_stan = result.PosStan || false;
        paymentLine._markDirty?.();
        return true;
    },
});

patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation() {
        const ok = await super.askBeforeValidation();
        if (ok === false) {
            return false;
        }

        let collectedRrn = "";
        for (const paymentLine of this.order.payment_ids || []) {
            if (!paymentLine.payment_method_id?.meps_enabled) {
                continue;
            }
            if (!paymentLine.meps_rrn) {
                this.pos.dialog.add(AlertDialog, {
                    title: _t("Incomplete MEPS Payment"),
                    body: _t("A MEPS payment line is missing terminal confirmation. Remove it and retry."),
                });
                return false;
            }
            if (!collectedRrn) {
                collectedRrn = paymentLine.meps_rrn;
            }
        }

        this.order.mep_id = collectedRrn || false;
        this.order._markDirty?.();
        return true;
    },
});

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        this.mep_id = vals?.mep_id || this.mep_id || false;
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        data.mep_id = this.mep_id || false;
        return data;
    },
});

const MEPS_PAYMENT_FIELDS = [
    "meps_rrn",
    "meps_auth_code",
    "meps_resp_code",
    "meps_resp_text",
    "meps_card_pan",
    "meps_card_entry_mode",
    "meps_batch_number",
    "meps_stan",
];

patch(PosPayment.prototype, {
    setup(vals) {
        super.setup(vals);
        for (const field of MEPS_PAYMENT_FIELDS) {
            this[field] = vals?.[field] || this[field] || false;
        }
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        for (const field of MEPS_PAYMENT_FIELDS) {
            data[field] = this[field] || false;
        }
        return data;
    },
});
