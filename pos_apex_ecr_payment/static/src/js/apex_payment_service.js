/** @odoo-module **/
/**
 * ApexPaymentService
 *
 * Low-level service that wraps every Apex ECR backend route.
 * Imported by apex_payment_method.js — not meant to be used directly
 * from OWL components.
 */

import { jsonrpc } from "@web/core/network/rpc";

export const ApexPaymentService = {

    /**
     * Send a SALE request to the Apex terminal.
     *
     * @param {number}  paymentMethodId  - pos.payment.method id
     * @param {number}  amount           - decimal amount e.g. 13.500
     * @param {string}  invoiceNumber    - up to 6-char ECR invoice number
     * @param {string}  [referenceNumber]
     * @returns {Promise<Object>}  parsed Apex response
     */
    async sale(paymentMethodId, amount, invoiceNumber, referenceNumber = "") {
        return jsonrpc("/apex_ecr/sale", {
            payment_method_id: paymentMethodId,
            amount: amount,
            invoice_number: invoiceNumber,
            reference_number: referenceNumber,
        });
    },

    /**
     * Send a REFUND request.
     */
    async refund(paymentMethodId, amount, invoiceNumber, referenceNumber = "") {
        return jsonrpc("/apex_ecr/refund", {
            payment_method_id: paymentMethodId,
            amount: amount,
            invoice_number: invoiceNumber,
            reference_number: referenceNumber,
        });
    },

    /**
     * VOID a previous transaction by its original EFTPOS invoice number.
     */
    async void(paymentMethodId, originalInvoiceNumber) {
        return jsonrpc("/apex_ecr/void", {
            payment_method_id: paymentMethodId,
            original_invoice_number: originalInvoiceNumber,
        });
    },

    /**
     * Cancel the last in-progress request on the terminal.
     */
    async cancel(paymentMethodId) {
        return jsonrpc("/apex_ecr/cancel", {
            payment_method_id: paymentMethodId,
        });
    },

    /**
     * ECR Enquiry — recover a transaction that was approved at POS
     * but lost at ECR level.
     */
    async enquiry(paymentMethodId, origInvoiceNumber, origRrn = "", origAuthCode = "") {
        return jsonrpc("/apex_ecr/enquiry", {
            payment_method_id: paymentMethodId,
            orig_invoice_number: origInvoiceNumber,
            orig_rrn: origRrn,
            orig_auth_code: origAuthCode,
        });
    },

    /**
     * Persist approved Apex response fields on a pos.payment record.
     */
    async savePaymentData(posPaymentId, apexData) {
        return jsonrpc("/apex_ecr/save_payment_data", {
            pos_payment_id: posPaymentId,
            apex_data: apexData,
        });
    },
};
