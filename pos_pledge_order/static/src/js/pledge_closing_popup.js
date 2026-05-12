/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

patch(ClosePosPopup.prototype, {
    pledgeCashLineLabel() {
        return _t("Pledge deposits");
    },

    pledgeBankLineLabel(pm) {
        const name = pm?.name || "";
        return name ? `${_t("Pledge deposits")}: ${name}` : _t("Pledge deposits");
    },

    shouldShowPledgeCashLine() {
        const dc = this.props.default_cash_details || {};
        const amt = dc.pledge_payment_amount ?? 0;
        return !!(amt && this.pos.currency && !this.pos.currency.isZero(amt));
    },

    shouldShowPledgeBankLine(pm) {
        const amt = pm?.pledge_payment_amount ?? 0;
        return !!(amt && this.pos.currency && !this.pos.currency.isZero(amt));
    },
});
