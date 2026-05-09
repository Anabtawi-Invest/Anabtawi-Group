/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

patch(ClosePosPopup.prototype, {
    pledgeCashLineLabel() {
        return _t("Pledge (POS Advance Account)");
    },

    pledgeBankLineLabel(pm) {
        const name = pm?.name || "";
        return name
            ? `${_t("Pledge (POS Advance Account)")}: ${name}`
            : _t("Pledge (POS Advance Account)");
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
