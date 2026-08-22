/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { promptAndApplyOnsitePricing, isOrderOnSite, logOnsite } from "@pos_onsite_price/js/onsite_price_utils";
import { applySiteServiceToPosOrder } from "@pos_advance_order/js/site_service_utils";

async function syncSiteServiceBeforePayment(pos) {
    const order = pos.getOrder?.() || pos.get_order?.();
    if (!order) {
        return;
    }
    const isOnSite = isOrderOnSite(order);
    const result = await applySiteServiceToPosOrder(pos, order, isOnSite);
    logOnsite("pay: sync site service (skipped prompt)", { isOnSite, result });
}

patch(PosStore.prototype, {
    async pay() {
        const result = await promptAndApplyOnsitePricing({
            pos: this,
            dialog: this.dialog || this.env?.services?.dialog,
            notification: this.notification || this.env?.services?.notification,
            stayMessage: _t("Prices updated. Press Payment again to continue."),
            source: "pay",
        });
        if (result?.cancelled || result?.error) {
            return;
        }
        if (result?.applied) {
            return;
        }
        if (result?.skipped) {
            await syncSiteServiceBeforePayment(this);
        }
        return await super.pay(...arguments);
    },

    async validateOrderFast(paymentMethod) {
        const result = await promptAndApplyOnsitePricing({
            pos: this,
            dialog: this.dialog || this.env?.services?.dialog,
            notification: this.notification || this.env?.services?.notification,
            stayMessage: _t("Prices updated. Press Payment again to continue."),
            source: "pay_fast",
        });
        if (result?.cancelled || result?.error) {
            return;
        }
        if (result?.applied) {
            return;
        }
        if (result?.skipped) {
            await syncSiteServiceBeforePayment(this);
        }
        return await super.validateOrderFast(paymentMethod);
    },
});

patch(PaymentScreen.prototype, {
    _checkPledgeItems(order) {
        if (isOrderOnSite(order)) {
            return false;
        }
        return super._checkPledgeItems(...arguments);
    },
});
