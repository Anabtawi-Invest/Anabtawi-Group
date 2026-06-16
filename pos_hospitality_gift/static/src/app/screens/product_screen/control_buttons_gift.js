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

        selectedLine.update({ is_gift: !selectedLine.is_gift });
    },
});
