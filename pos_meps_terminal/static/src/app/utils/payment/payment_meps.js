import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/services/pos_store";

// PDF spec 4.3 <PosCardEntryModeId> / DLL EcrCardData.PosCardEntryModeId
const ENTRY_MODE_LABELS = {
    "0": "Unknown",
    "1": "Manual",
    "2": "Swipe",
    "3": "Chip",
    "4": "Fallback",
    "5": "Contactless",
    "6": "Mobile",
};

export class PaymentMeps extends PaymentInterface {
    sendPaymentRequest(uuid) {
        super.sendPaymentRequest(uuid);
        return this._mepsPay(uuid);
    }

    sendPaymentCancel(order, uuid) {
        super.sendPaymentCancel(order, uuid);
        // MEPS/ApexECR does not expose a live in-flight abort over this web service;
        // the Sale request already sent to the terminal cannot be cancelled from here.
        return Promise.resolve(true);
    }

    async _mepsPay(uuid) {
        const line = this.pos.getOrder().payment_ids.find((l) => l.uuid === uuid);
        if (!line) {
            return false;
        }
        if (line.amount <= 0) {
            this._showError(_t("Cannot process transactions with a zero or negative amount."));
            return false;
        }

        const order = this.pos.getOrder();
        const invoiceNumber = String(order.pos_reference || order.uuid || "").slice(-8);
        const referenceNumber = order.uuid || "";

        let result;
        try {
            result = await this.pos.data.call("pos.payment.method", "meps_sale", [
                [this.payment_method_id.id],
                line.amount,
                invoiceNumber,
                referenceNumber,
            ]);
        } catch (error) {
            this._showError(
                error?.data?.message || error?.message || _t("Could not reach the MEPS payment gateway.")
            );
            return false;
        }

        const approved = result?.WebResponseStatus === "Success" && result?.PosRespStatus === "1";
        if (!approved) {
            this._showError(
                result?.WebResponseErrorDesc ||
                    result?.PosRespText ||
                    _t("The MEPS terminal declined the transaction.")
            );
            return false;
        }

        line.card_brand = result.PosIssuerName || "";
        line.card_no = result.PosPan || "";
        line.payment_ref_no = result.PosRRN || "";
        line.payment_method_authcode = result.PosAuthCode || "";
        line.transaction_id = result.PosStan || "";
        line.payment_method_payment_mode = ENTRY_MODE_LABELS[result.PosCardEntryModeId] || "";
        if (result.PosReceipt) {
            line.setReceiptInfo(result.PosReceipt);
        }
        return true;
    }

    _showError(msg, title) {
        this.env.services.dialog.add(AlertDialog, {
            title: title || _t("MEPS Payment Error"),
            body: msg,
        });
    }
}

register_payment_method("meps", PaymentMeps);
