/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

patch(ControlButtons.prototype, {
    toggleGiftLine() {
        const order = this.currentOrder;
        const selectedLine = order?.getSelectedOrderline?.();
        if (!selectedLine) {
            this.notification.add(_t("Please select an order line first."), {
                type: "warning",
            });
            return;
        }

        const wasGift = Boolean(selectedLine.is_gift);
        if (!wasGift) {
            selectedLine._gift_previous_discount = selectedLine.discount || 0;
            selectedLine.set_discount(100);
        } else {
            const previousDiscount =
                typeof selectedLine._gift_previous_discount === "number"
                    ? selectedLine._gift_previous_discount
                    : 0;
            selectedLine.set_discount(previousDiscount);
            delete selectedLine._gift_previous_discount;
        }

        selectedLine.update({ is_gift: !wasGift });
    },
});
