/** @odoo-module **/
/**
 * Apex ECR Payment Method — Odoo 19 OWL Integration
 *
 * What this file does:
 *  1. Defines ApexPaymentDialog — an OWL Component that overlays the
 *     PaymentScreen while the cashier waits for the terminal.
 *  2. Patches PaymentScreen.sendPayment (the method called when the
 *     cashier clicks "Send" / validates with an Apex payment line) so
 *     that it intercepts Apex payment methods and shows the dialog.
 *  3. Loads Apex fields from pos.payment.method into the POS session
 *     via a PosGlobalState patch.
 *
 * Transaction flow:
 *  Cashier adds payment line → clicks Validate →
 *  sendPayment() detects Apex method →
 *  shows ApexPaymentDialog (waiting state) →
 *  calls /apex_ecr/sale (or /refund) →
 *  on success  → dialog shows "Approved", then closes & order validates
 *  on declined → dialog shows "Declined", cashier dismisses manually
 *  on Cancel   → calls /apex_ecr/cancel, dialog closes
 */

import { Component, useState, onMounted } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ApexPaymentService } from "./apex_payment_service";

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Format an Odoo POS amount to a plain decimal string with 3 decimal places
 * (Apex expects e.g. "13.500").
 */
function formatApexAmount(amount) {
    return parseFloat(amount).toFixed(3);
}

/**
 * Generate a simple invoice number from the current order name + timestamp
 * to keep it within the 6-char limit expected by Apex.
 * We use the last 6 digits of Date.now() as a fallback.
 */
function generateInvoiceNumber(order) {
    if (order && order.name) {
        // e.g. "Order 00042" → "000042"
        const digits = order.name.replace(/\D/g, "").slice(-6).padStart(6, "0");
        if (digits.length === 6) return digits;
    }
    return String(Date.now()).slice(-6);
}

// ─── ApexPaymentDialog ────────────────────────────────────────────────────────

class ApexPaymentDialog extends Component {
    static template = "pos_apex_ecr_payment.ApexPaymentDialog";

    setup() {
        this.state = useState({
            /** "waiting" | "approved" | "declined" | "error" */
            status: "waiting",
            amountLabel: this.props.amountLabel || "",
            result: {},
            errorMessage: "",
        });

        onMounted(() => this._doTransaction());
    }

    /**
     * Executes the Apex transaction.  The type (sale / refund) is
     * determined by props.transactionType.
     */
    async _doTransaction() {
        const { paymentMethodId, amount, invoiceNumber, referenceNumber, transactionType } = this.props;

        try {
            let result;
            if (transactionType === "REFUND") {
                result = await ApexPaymentService.refund(
                    paymentMethodId, amount, invoiceNumber, referenceNumber
                );
            } else {
                result = await ApexPaymentService.sale(
                    paymentMethodId, amount, invoiceNumber, referenceNumber
                );
            }

            if (result.success) {
                this.state.status = "approved";
                this.state.result = result;
                // Auto-close after 2 s on approval so the cashier isn't blocked
                setTimeout(() => this.props.onApproved(result), 2000);
            } else {
                this.state.status = "declined";
                this.state.result = result;
            }
        } catch (err) {
            this.state.status = "error";
            this.state.errorMessage = String(err.message || err);
        }
    }

    /** Cancel button: tell the terminal to cancel, then close dialog. */
    async onCancel() {
        try {
            await ApexPaymentService.cancel(this.props.paymentMethodId);
        } catch (_) {
            // Ignore cancel errors — terminal may have already timed out
        }
        this.props.onCancelled();
    }

    /** Close / dismiss button (after declined or error). */
    onClose() {
        this.props.onDismissed(this.state);
    }
}

// ─── Patch PosGlobalState ─────────────────────────────────────────────────────
// Load apex_enabled and related fields from pos.payment.method so the
// frontend knows which payment methods are Apex ECR methods.

try {
    const { PosGlobalState } = await odoo.loader.modules.get(
        "@point_of_sale/app/store/pos_store"
    );

    patch(PosGlobalState.prototype, {
        /**
         * After the standard payment method objects are loaded, annotate each
         * one that has apex_enabled = true.
         */
        async _processData(loadedData) {
            await super._processData(loadedData);
            // payment_methods is keyed by id in Odoo 19 PosGlobalState
            for (const pm of Object.values(this.payment_methods_by_id || {})) {
                // The server serialises Boolean fields normally
                pm.apex_enabled = !!pm.apex_enabled;
            }
        },
    });
} catch (_) {
    // PosGlobalState patch is best-effort; fields will still exist on the
    // payment method object if the server serialises them.
}

// ─── Patch PaymentScreen ──────────────────────────────────────────────────────

patch(PaymentScreen.prototype, {

    setup() {
        super.setup();
        this.pos = usePos();
        // Track whether an Apex dialog is currently open to prevent double-submit
        this._apexDialogActive = false;
    },

    /**
     * Override validateOrder to intercept Apex payments.
     * Odoo 19 calls this when the cashier presses "Validate".
     */
    async validateOrder(isForceValidate) {
        const order = this.pos.get_order();
        if (!order) return super.validateOrder(isForceValidate);

        // Find pending payment lines that use an Apex method and haven't
        // been processed yet (no auth code stored).
        const apexLines = order.get_paymentlines().filter(
            (line) =>
                line.payment_method.apex_enabled &&
                !line.apex_auth_code
        );

        if (apexLines.length === 0) {
            // No Apex lines pending — proceed normally
            return super.validateOrder(isForceValidate);
        }

        if (this._apexDialogActive) return;

        // Process the first pending Apex line
        const line = apexLines[0];
        await this._processApexLine(line, order);
        // After processing (approve/decline/cancel) re-check whether we can
        // now validate the order.
        if (!line.apex_auth_code) {
            // Not approved — do not validate
            return;
        }
        return super.validateOrder(isForceValidate);
    },

    /**
     * Show the ApexPaymentDialog for a given payment line.
     * Returns a promise that resolves when the dialog is dismissed.
     */
    _processApexLine(line, order) {
        return new Promise((resolve) => {
            this._apexDialogActive = true;

            const pm = line.payment_method;
            const amount = formatApexAmount(line.get_amount());
            const invoiceNumber = generateInvoiceNumber(order);
            const isRefund = order.get_total_with_tax() < 0;

            // Mount the dialog into a dedicated container div
            const container = document.createElement("div");
            container.className = "apex-dialog-mount";
            document.body.appendChild(container);

            const cleanup = () => {
                this._apexDialogActive = false;
                container.remove();
                resolve();
            };

            // We use Owl's mount helper to render the dialog component
            // in the existing Owl app environment.
            const app = this.__owl__.app;
            app.mount(ApexPaymentDialog, container, {
                props: {
                    paymentMethodId: pm.id,
                    amount: amount,
                    amountLabel: `${amount} ${pm.apex_currency_code || "JOD"}`,
                    invoiceNumber: invoiceNumber,
                    referenceNumber: order.name || "",
                    transactionType: isRefund ? "REFUND" : "SALE",

                    onApproved: async (result) => {
                        // Store auth code on the payment line so the guard above
                        // knows not to re-process it.
                        line.apex_auth_code = result.auth_code;
                        line.apex_result = result;
                        // The dialog auto-closes via setTimeout in the component;
                        // we just need to release the promise after the auto-close.
                        setTimeout(cleanup, 2100);
                    },

                    onCancelled: () => {
                        // Remove the payment line so the cashier can try again
                        order.remove_paymentline(line);
                        cleanup();
                    },

                    onDismissed: (finalState) => {
                        if (finalState.status === "declined") {
                            // Remove the line — cashier must re-add and retry
                            order.remove_paymentline(line);
                        }
                        cleanup();
                    },
                },
            });
        });
    },
});
