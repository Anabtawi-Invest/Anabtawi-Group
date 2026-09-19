/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import {
    promptAndApplyOnsitePricing,
    shouldSkipPledge,
    getOrderServiceType,
    getOnsiteUiState,
    logOnsite,
    SERVICE_TYPE,
} from "@pos_onsite_price/js/onsite_price_utils";
import { applySiteServiceToPosOrder } from "@pos_advance_order/js/site_service_utils";
import { applyOnsitePledgeLinesToPosOrder } from "@pos_onsite_price/js/onsite_pledge_lines";

async function syncSiteServiceBeforePayment(pos) {
    const order = pos.getOrder?.() || pos.get_order?.();
    if (!order) {
        return;
    }
    const serviceType = getOrderServiceType(order);
    const state = getOnsiteUiState(order);
    const options =
        serviceType === SERVICE_TYPE.ON_SITE
            ? { serviceType, unitPrice: Number(state?.servicePrice || 0) }
            : serviceType === SERVICE_TYPE.CUTTING
              ? { serviceType, unitPrice: Number(state?.cuttingServicePrice || 0) }
              : { serviceType: SERVICE_TYPE.NONE };
    const result = await applySiteServiceToPosOrder(pos, order, options);
    // None (and unanswered) → add pledges. Site Service / Cutting → remove/skip.
    const skipPledge = shouldSkipPledge(order);
    const pledgeResult = await applyOnsitePledgeLinesToPosOrder(pos, order, skipPledge);
    logOnsite("pay: sync site/cutting service + pledge lines", {
        serviceType,
        skipPledge,
        options,
        result,
        pledgeResult,
    });
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
            // Stay on product screen so cashier sees new prices / pledge lines.
            return;
        }
        // skipped or answered with no cart change — sync pledge/service before payment.
        await syncSiteServiceBeforePayment(this);
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
        await syncSiteServiceBeforePayment(this);
        return await super.validateOrderFast(paymentMethod);
    },
});

patch(PaymentScreen.prototype, {
    _checkPledgeItems(order) {
        // Only Site Service / Cutting skip pledge creation. None keeps pledges.
        if (shouldSkipPledge(order)) {
            return false;
        }
        return super._checkPledgeItems(...arguments);
    },
});
