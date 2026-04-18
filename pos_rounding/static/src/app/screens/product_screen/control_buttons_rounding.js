/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { _t } from "@web/core/l10n/translation";

patch(ControlButtons.prototype, {
    async applyRounding() {
        const order = this.currentOrder;
        if (!order) {
            return;
        }

        if (!order.getOrderlines().length) {
            this.notification.add(_t("There are no products in the order."), { type: "warning" });
            return;
        }

        const payload = await makeAwaitable(this.dialog, NumberPopup, {
            title: _t("Enter Rounding Amount"),
            startingValue: order.getOpenAmount?.() || 0,
        });

        if (payload === undefined) {
            return;
        }

        const amountWithTax = this.env.utils.parseValidFloat(payload?.toString() || "");
        if (isNaN(amountWithTax) || amountWithTax <= 0) {
            this.notification.add(_t("Please enter a valid amount."), { type: "warning" });
            return;
        }

        if (amountWithTax > 0.099) {
            this.notification.add(_t("Maximum allowed rounding amount is 0.099."), {
                type: "warning",
            });
            return;
        }

        order.setOpenAmount?.(Math.abs(amountWithTax));
    },
});
