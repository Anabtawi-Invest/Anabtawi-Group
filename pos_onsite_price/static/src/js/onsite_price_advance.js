/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { promptAndApplyOnsitePricing } from "@pos_onsite_price/js/onsite_price_utils";

patch(ControlButtons.prototype, {
    async onClickAdvanceOrder() {
        const result = await promptAndApplyOnsitePricing({
            pos: this.pos,
            dialog: this.dialog,
            notification: this.notification,
            stayMessage: _t("On-site prices applied. Continue with the advance order."),
        });
        if (result?.cancelled || result?.error) {
            return;
        }
        return await super.onClickAdvanceOrder(...arguments);
    },
});
