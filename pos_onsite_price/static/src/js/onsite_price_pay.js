/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { promptAndApplyOnsitePricing } from "@pos_onsite_price/js/onsite_price_utils";

patch(PosStore.prototype, {
    async pay() {
        const result = await promptAndApplyOnsitePricing({
            pos: this,
            dialog: this.dialog || this.env?.services?.dialog,
            notification: this.notification || this.env?.services?.notification,
            stayMessage: _t("Prices updated. Press Payment again to continue."),
        });
        if (result?.cancelled || result?.error) {
            return;
        }
        if (result?.applied) {
            return;
        }
        return await super.pay(...arguments);
    },

    async validateOrderFast(paymentMethod) {
        const result = await promptAndApplyOnsitePricing({
            pos: this,
            dialog: this.dialog || this.env?.services?.dialog,
            notification: this.notification || this.env?.services?.notification,
            stayMessage: _t("Prices updated. Press Payment again to continue."),
        });
        if (result?.cancelled || result?.error) {
            return;
        }
        if (result?.applied) {
            return;
        }
        return await super.validateOrderFast(paymentMethod);
    },
});
