/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";
import { ConnectionLostError, RPCError } from "@web/core/network/rpc";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import { DeliveryAmountPopup } from "@pos_delivery_amount/app/components/delivery_amount_popup/delivery_amount_popup";

patch(ClosePosPopup.prototype, {
    _showDeliveryAmountError(message) {
        this.dialog.add(AlertDialog, {
            title: _t("Delivery Amount"),
            body: message || _t("An error occurred while processing Delivery Amount."),
        });
    },

    _extractDeliveryAmountErrorMessage(error) {
        if (error instanceof RPCError) {
            return (
                error?.data?.arguments?.[0] ||
                error?.data?.message ||
                error?.message ||
                _t("An error occurred while processing Delivery Amount.")
            );
        }
        return error?.message || _t("An error occurred while processing Delivery Amount.");
    },

    async _askDeliveryAmount(countedCashBalance) {
        while (true) {
            const result = await makeAwaitable(this.dialog, DeliveryAmountPopup, {
                defaultAmount: 0,
                maxAmount: countedCashBalance,
                title: _t("Delivery Amount"),
                fieldLabel: _t("Delivery Amount"),
            });

            if (result === undefined) {
                return undefined;
            }

            if (result < 0) {
                this.dialog.add(AlertDialog, {
                    title: _t("Delivery Amount"),
                    body: _t("Delivery Amount must be positive or zero."),
                });
                continue;
            }

            if (result > countedCashBalance) {
                this.dialog.add(AlertDialog, {
                    title: _t("Delivery Amount"),
                    body: _t("Delivery Amount cannot exceed counted cash balance."),
                });
                continue;
            }

            if (this.pos.currency.isZero(result)) {
                const proceed = await ask(this.dialog, {
                    title: _t("Delivery Amount"),
                    body: _t("Are you sure the Delivery Amount is zero?"),
                    confirmLabel: _t("Yes"),
                    cancelLabel: _t("No"),
                });
                if (!proceed) {
                    continue;
                }
            }

            return result;
        }
    },

    _getCountedCashBalance() {
        if (!this.pos.config.cash_control || !this.props.default_cash_details?.id) {
            return 0;
        }
        return this.env.utils.parseValidFloat(
            this.state.payments[this.props.default_cash_details.id].counted
        );
    },

    async closeSession() {
        this.pos._resetConnectedCashier();
        const syncSuccess = await this.pos.pushOrdersWithClosingPopup();
        if (!syncSuccess) {
            return;
        }

        if (this.pos.config.cash_control) {
            const response = await this.pos.data.call(
                "pos.session",
                "post_closing_cash_details",
                [this.pos.session.id],
                {
                    counted_cash: this._getCountedCashBalance(),
                }
            );

            if (!response.successful) {
                return this.handleClosingError(response);
            }
        }

        const countedCashBalance = this._getCountedCashBalance();
        const deliveryAmount = await this._askDeliveryAmount(countedCashBalance);
        if (deliveryAmount === undefined) {
            return;
        }

        try {
            await this.pos.data.call("pos.session", "update_closing_control_state_session", [
                this.pos.session.id,
                this.state.notes,
            ]);
        } catch (error) {
            // Keep original close flow error behavior for rescue/manual closing fallback.
            if (!error.data && error.data.message !== "This session is already closed.") {
                throw error;
            }
        }

        let deliveryResponse;
        try {
            deliveryResponse = await this.pos.data.call(
                "pos.session",
                "action_process_delivery_amount",
                [this.pos.session.id, deliveryAmount]
            );
        } catch (error) {
            if (error instanceof ConnectionLostError) {
                throw error;
            }
            this._showDeliveryAmountError(this._extractDeliveryAmountErrorMessage(error));
            return;
        }
        if (!deliveryResponse?.successful) {
            return this.handleClosingError(deliveryResponse);
        }

        try {
            const bankPaymentMethodDiffPairs = this.props.non_cash_payment_methods
                .filter((pm) => pm.type == "bank")
                .map((pm) => [pm.id, this.getDifference(pm.id)]);
            const response = await this.pos.data.call(
                "pos.session",
                "close_session_from_ui",
                [this.pos.session.id, bankPaymentMethodDiffPairs],
                {
                    context: {
                        device_identifier: this.pos.device.identifier,
                    },
                }
            );
            if (!response.successful) {
                return this.handleClosingError(response);
            }
            this.pos.session.state = "closed";
            this.pos.router.close();
        } catch (error) {
            if (error instanceof ConnectionLostError) {
                throw error;
            } else {
                await this.handleClosingControlError();
            }
        } finally {
            localStorage.removeItem(`pos.session.${odoo.pos_config_id}`);
        }
    },
});
