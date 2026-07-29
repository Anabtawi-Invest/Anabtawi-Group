/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ConnectionLostError } from "@web/core/network/rpc";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import {
    askDeliveryAmount,
    fetchDeliveryAmountPopupData,
    processDeliveryAmount,
} from "@pos_delivery_amount/app/utils/delivery_amount_flow";

patch(ClosePosPopup.prototype, {
    get deliveryMoveData() {
        const moves = this.props.default_cash_details?.delivery_moves || [];
        return {
            total: this.props.default_cash_details?.delivery_total ?? 0,
            moves: moves.map((move, index) => ({
                id: move.id ?? index,
                name: move.name,
                amount: move.amount,
            })),
        };
    },

    shouldShowCashDeliveryLine() {
        const total = this.props.default_cash_details?.delivery_total ?? 0;
        return !!(this.pos.currency && !this.pos.currency.isZero(total));
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

        let popupData = { configured: false, max_amount: 0, delivered_total: 0 };
        try {
            popupData = await fetchDeliveryAmountPopupData(this.pos);
        } catch (error) {
            console.warn("[pos_delivery_amount] Could not load delivery popup data.", error);
        }

        if (popupData.configured) {
            const deliveryAmount = await askDeliveryAmount(this.dialog, {
                maxAmount: popupData.max_amount,
                deliveredTotal: popupData.delivered_total,
            });
            if (deliveryAmount === undefined) {
                return;
            }

            await this._waitForDialogRenderCycle();

            const deliveryResponse = await processDeliveryAmount(
                this.pos,
                this.dialog,
                deliveryAmount
            );
            if (deliveryResponse === null) {
                return;
            }
            if (!deliveryResponse?.successful) {
                return this.handleClosingError(deliveryResponse);
            }
        }

        try {
            await this.pos.data.call("pos.session", "update_closing_control_state_session", [
                this.pos.session.id,
                this.state.notes,
            ]);
        } catch (error) {
            if (!error.data && error.data.message !== "This session is already closed.") {
                throw error;
            }
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

    async _waitForDialogRenderCycle() {
        await new Promise((resolve) => requestAnimationFrame(resolve));
    },

    _getCountedCashBalance() {
        if (!this.pos.config.cash_control || !this.props.default_cash_details?.id) {
            return 0;
        }
        return this.env.utils.parseValidFloat(
            this.state.payments[this.props.default_cash_details.id].counted
        );
    },
});
