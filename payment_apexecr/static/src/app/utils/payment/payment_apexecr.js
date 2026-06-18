import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/services/pos_store";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { rpc } from "@web/core/network/rpc";

function absNumber(v) {
    const n = typeof v === "number" ? v : parseFloat(v || 0);
    return Math.abs(Number.isFinite(n) ? n : 0);
}

function genRef(order, uuid) {
    const token = ((order?.uuid || "") + (uuid || "")).replace(/[^A-Za-z0-9]/g, "").slice(0, 18);
    const ts = String(Date.now()).slice(-8);
    return `OD${token}${ts}`.slice(0, 30);
}

function genInvoice(order) {
    const token = (order?.uid || order?.name || "").replace(/[^A-Za-z0-9]/g, "");
    return (token || String(Date.now()).slice(-6)).slice(-30);
}

function buildApexReceipt({
    amount,
    referenceNumber,
    invoiceNumber,
    rrn,
    authCode,
    responseCode,
    responseText,
    transactionType,
}) {
    const rows = [
        "APEXECR",
        `TYPE: ${transactionType || ""}`,
        `AMOUNT: ${amount ?? ""}`,
        `REF: ${referenceNumber || ""}`,
        `INV: ${invoiceNumber || ""}`,
        `RRN: ${rrn || ""}`,
        `AUTH: ${authCode || ""}`,
        `RESP: ${responseCode || ""} ${responseText || ""}`.trim(),
    ];
    return rows.join("\n");
}

export class PaymentApexEcr extends PaymentInterface {
    setup() {
        super.setup(...arguments);
    }

    get fastPayments() {
        return false;
    }

    _showError(body, title = _t("ApexECR Error")) {
        this.env.services.dialog.add(AlertDialog, { title, body });
    }

    async sendPaymentRequest(uuid) {
        const order = this.pos.getOrder();
        const line = order?.payment_ids?.find((pl) => pl.uuid === uuid) || order?.getSelectedPaymentline();
        if (!line) {
            return false;
        }
        super.sendPaymentRequest(uuid);
        const amountAbs = absNumber(line.amount);
        if (!amountAbs) {
            this._showError(_t("Amount must be greater than zero."));
            line.setPaymentStatus("retry");
            return false;
        }
        const isRefund = Boolean(order?.isRefund);
        const referenceNumber = genRef(order, uuid);
        const invoiceNumber = genInvoice(order);
        line.apexecr_reference_number = referenceNumber;
        line.apexecr_invoice_number = invoiceNumber;
        line.apexecr_sync_state = "none";

        const payload = {
            payment_method_id: this.payment_method_id.id,
            amount: amountAbs,
            transaction_type: isRefund ? "REFUND" : "SALE",
            reference_number: referenceNumber,
            invoice_number: invoiceNumber,
            orig_rrn: line.uiState?.apexecr_parent_rrn || null,
            orig_auth_code: line.uiState?.apexecr_parent_auth_code || null,
        };
        if (isRefund && !payload.orig_rrn && !payload.orig_auth_code) {
            this._showError(_t("Missing original Apex references for refund (RRN/AuthCode)."));
            line.setPaymentStatus("retry");
            return false;
        }
        line.setPaymentStatus("waitingCard");
        let response;
        try {
            response = await rpc("/pos_apexecr/financial", payload);
        } catch (e) {
            this._showError(_t("Could not reach Odoo ApexECR service."));
            line.setPaymentStatus("retry");
            return false;
        }
        if (!response?.ok) {
            this._showError(response?.error || _t("ApexECR request failed."));
            line.setPaymentStatus("retry");
            return false;
        }

        const result = response.result || {};
        line.apexecr_rrn = result.rrn || "";
        line.apexecr_auth_code = result.auth_code || "";
        line.apexecr_response_code = result.response_code || "";
        line.apexecr_response_text = result.response_text || "";
        line.apexecr_web_status = result.web_status || "";
        line.apexecr_pos_status = result.pos_status;
        line.apexecr_transaction_name = result.txn_name || payload.transaction_type;
        line.apexecr_masked_pan = result.masked_pan || "";
        line.apexecr_raw_response = result.raw_response || "";
        line.apexecr_sync_state = result.sync_state || "error";
        line.transaction_id = result.rrn || result.auth_code || line.transaction_id;
        line.payment_method_authcode = result.auth_code || line.payment_method_authcode;
        line.setReceiptInfo(
            buildApexReceipt({
                amount: amountAbs.toFixed(2),
                referenceNumber,
                invoiceNumber,
                rrn: result.rrn || "",
                authCode: result.auth_code || "",
                responseCode: result.response_code || "",
                responseText: result.response_text || "",
                transactionType: payload.transaction_type,
            })
        );

        if (result.approved) {
            line.setPaymentStatus("done");
            return true;
        }

        if (result.sync_state === "pending") {
            this._showError(
                _t("Transaction status is unknown on terminal side. It will be reconciled automatically."),
                _t("ApexECR Pending")
            );
            line.setPaymentStatus("retry");
            return false;
        }

        this._showError(result.response_text || _t("Transaction declined."));
        line.setPaymentStatus("retry");
        return false;
    }
}

register_payment_method("apexecr", PaymentApexEcr);

