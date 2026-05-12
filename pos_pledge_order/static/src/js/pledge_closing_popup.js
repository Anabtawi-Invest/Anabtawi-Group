/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

patch(ClosePosPopup.prototype, {
    pledgeCashLineLabel() {
        const dc = this.props.default_cash_details || {};
        const amt = Number(dc.pledge_payment_amount ?? 0);
        if (amt < 0) {
            return _t("Pledge returns (cash out)");
        }
        return _t("Pledge deposits (cash in)");
    },

    pledgeBankLineLabel(pm) {
        const name = pm?.name || "";
        const amt = Number(pm?.pledge_payment_amount ?? 0);
        const suffix =
            amt < 0 ? _t("Pledge returns") : _t("Pledge deposits");
        if (name) {
            return `${suffix}: ${name}`;
        }
        return suffix;
    },

    shouldShowPledgeCashLine() {
        const dc = this.props.default_cash_details || {};
        const amt = dc.pledge_payment_amount ?? 0;
        return !!(this.pos.currency && !this.pos.currency.isZero(amt));
    },

    shouldShowPledgeBankLine(pm) {
        const amt = pm?.pledge_payment_amount ?? 0;
        return !!(this.pos.currency && !this.pos.currency.isZero(amt));
    },
});
