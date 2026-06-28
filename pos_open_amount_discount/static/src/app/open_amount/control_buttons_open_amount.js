/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import {
    applyOpenAmountDiscount,
    getApplicableLines,
    toNumber,
} from "@pos_open_amount_discount/app/open_amount/open_amount_utils";

patch(ControlButtons.prototype, {
    get isOpenAmountEnabled() {
        return toNumber(this.pos.config?.maximum_open_amount) > 0;
    },

    get maximumOpenAmount() {
        return toNumber(this.pos.config?.maximum_open_amount);
    },

    async clickOpenAmount() {
        const order = this.currentOrder;
        if (!order) {
            return;
        }

        if (!this.isOpenAmountEnabled) {
            return;
        }

        if (!getApplicableLines(order).length) {
            this.notification.add(_t("There are no products in the order."), {
                type: "warning",
            });
            return;
        }

        const maxAmount = this.maximumOpenAmount;
        const parseAmount = (buffer) =>
            this.env.utils.parseValidFloat((buffer ?? "").toString());

        const payload = await makeAwaitable(this.dialog, NumberPopup, {
            title: _t("Enter Open Amount"),
            startingValue: 0,
            isValid: (buffer) => {
                const amount = parseAmount(buffer);
                return Number.isFinite(amount) && amount > 0 && amount <= maxAmount;
            },
            feedback: (buffer) => {
                const amount = parseAmount(buffer);
                if (!buffer && buffer !== 0) {
                    return false;
                }
                if (!Number.isFinite(amount) || amount <= 0) {
                    return _t("Amount must be greater than 0.");
                }
                if (amount > maxAmount) {
                    return _t(
                        "Amount must not exceed the configured maximum of %s.",
                        this.env.utils.formatCurrency(maxAmount)
                    );
                }
                return false;
            },
        });

        if (payload === undefined) {
            return;
        }

        const enteredAmount = parseAmount(payload);
        if (!Number.isFinite(enteredAmount) || enteredAmount <= 0) {
            this.notification.add(_t("Amount must be greater than 0."), { type: "warning" });
            return;
        }
        if (enteredAmount > maxAmount) {
            this.notification.add(
                _t(
                    "Amount must not exceed the configured maximum of %s.",
                    this.env.utils.formatCurrency(maxAmount)
                ),
                { type: "warning" }
            );
            return;
        }

        const result = applyOpenAmountDiscount(order, enteredAmount);
        if (!result.success) {
            this.dialog.add(AlertDialog, {
                title: _t("Open Amount Error"),
                body: result.error || _t("Could not apply the open amount."),
            });
            return;
        }

        this.notification.add(
            _t("Open amount of %s applied.", this.env.utils.formatCurrency(enteredAmount)),
            { type: "success" }
        );
    },
});
