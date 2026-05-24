/** @odoo-module **/
// pos_delivery_amount/static/src/js/ClosePosPopupExtension.js

import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/navbar/close_pos_popup/close_pos_popup";
import { DeliveryAmountPopup } from "./DeliveryAmountPopup";
import { ConfirmPopup } from "@point_of_sale/app/popup/confirm_popup/confirm_popup";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

/**
 * Patch the standard ClosePosPopup to inject the Delivery Amount step
 * right before the session is actually closed.
 *
 * Flow:
 *  1. Show DeliveryAmountPopup
 *  2a. If amount == 0 → show zero-confirmation popup
 *      2a-YES → call server with 0, continue close
 *      2a-NO  → re-show DeliveryAmountPopup (loop)
 *  2b. If amount > 0 → call server, continue close on success
 *  3. On server error → show error, block close
 */
patch(ClosePosPopup.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
    },

    /**
     * Override the confirm handler to inject our popup before closing.
     */
    async confirm() {
        const continueClose = await this._handleDeliveryAmount();
        if (!continueClose) {
            // User cancelled or validation failed – do not close session.
            return;
        }
        // Proceed with standard Odoo session close
        await super.confirm();
    },

    // ----------------------------------------------------------------
    // Internal helpers
    // ----------------------------------------------------------------

    /**
     * Main orchestrator for the delivery amount workflow.
     * @returns {Promise<boolean>} true = proceed with close, false = abort
     */
    async _handleDeliveryAmount() {
        while (true) {
            const cashBalance = this._getCashBalance();
            const { confirmed, payload: deliveryAmount } = await this.popup.add(
                DeliveryAmountPopup,
                {
                    title: _t("Delivery Amount"),
                    cashBalance,
                }
            );

            if (!confirmed) {
                // Cashier pressed Cancel → abort session close
                return false;
            }

            if (deliveryAmount === 0) {
                const proceed = await this._confirmZeroAmount();
                if (proceed === "retry") {
                    // Cashier clicked "No" → go back to delivery popup
                    continue;
                }
                if (!proceed) {
                    return false;
                }
            }

            // Call backend
            const result = await this._callServerDeliveryAmount(deliveryAmount);
            if (!result.success) {
                await this.popup.add(ConfirmPopup, {
                    title: _t("Error"),
                    body: result.message,
                    cancelText: false,
                });
                // Stay in loop so cashier can correct
                continue;
            }

            return true;
        }
    },

    /**
     * Show zero-amount confirmation dialog.
     * @returns {Promise<true|'retry'|false>}
     *   true   = confirmed zero, proceed
     *   'retry'= cashier clicked No, re-show delivery popup
     *   false  = unexpected cancel
     */
    async _confirmZeroAmount() {
        const { confirmed } = await this.popup.add(ConfirmPopup, {
            title: _t("Confirm Zero Amount"),
            body: _t("Are you sure the Delivery Amount is zero?"),
            confirmText: _t("Yes"),
            cancelText: _t("No"),
        });
        if (confirmed) {
            return true;
        }
        return "retry";
    },

    /**
     * Retrieve the counted closing cash balance from the POS.
     * @returns {number}
     */
    _getCashBalance() {
        try {
            const session = this.pos.session;
            // Odoo 19: cash_register_balance_end_real holds the counted balance
            return session.cash_register_balance_end_real || 0;
        } catch {
            return 0;
        }
    },

    /**
     * RPC to backend action_process_delivery_amount.
     * @param {number} amount
     * @returns {Promise<{success: boolean, message: string}>}
     */
    async _callServerDeliveryAmount(amount) {
        try {
            const sessionId = this.pos.session.id;
            const result = await this.orm.call(
                "pos.session",
                "action_process_delivery_amount",
                [sessionId, amount],
                {}
            );
            return result;
        } catch (error) {
            return {
                success: false,
                message: _t("An unexpected server error occurred. Session closing aborted."),
            };
        }
    },
});
