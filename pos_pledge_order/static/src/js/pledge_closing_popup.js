/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

patch(ClosePosPopup.prototype, {
    pledgeCashInLabel() {
        return _t("Pledge deposits (cash in)");
    },

    pledgeCashOutLabel() {
        return _t("Pledge returns (cash out)");
    },

    pledgeBankInLabel(pm) {
        const name = pm?.name || "";
        return name
            ? sprintf(_t("Pledge deposit (%s)"), name)
            : _t("Pledge deposit");
    },

    pledgeBankOutLabel(pm) {
        const name = pm?.name || "";
        return name
            ? sprintf(_t("Pledge return (%s)"), name)
            : _t("Pledge return");
    },

    shouldShowPledgeCashInLine() {
        const dc = this.props.default_cash_details || {};
        const v = dc.pledge_cash_in ?? 0;
        return !!(this.pos.currency && !this.pos.currency.isZero(v));
    },

    shouldShowPledgeCashOutLine() {
        const dc = this.props.default_cash_details || {};
        const v = dc.pledge_cash_out ?? 0;
        return !!(this.pos.currency && !this.pos.currency.isZero(v));
    },

    shouldShowPledgeBankInLine(pm) {
        const v = pm?.pledge_pm_in ?? 0;
        return !!(this.pos.currency && !this.pos.currency.isZero(v));
    },

    shouldShowPledgeBankOutLine(pm) {
        const v = pm?.pledge_pm_out ?? 0;
        return !!(this.pos.currency && !this.pos.currency.isZero(v));
    },
});
