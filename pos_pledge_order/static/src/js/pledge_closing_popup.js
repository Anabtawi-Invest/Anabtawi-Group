/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

ClosePosPopup.props = [
    ...ClosePosPopup.props,
    "pledge_completion_details",
];

patch(ClosePosPopup.prototype, {
    pledgeCollectedTitle() {
        return _t("Pledges collected (advance completion)");
    },

    pledgeReturnedTitle() {
        return _t("Pledges returned");
    },

    pledgeCollectedCountLabel() {
        return _t("Pledge lines collected");
    },

    pledgeReturnedCountLabel() {
        return _t("Pledge lines returned");
    },

    pledgeReturnCashLabel() {
        return _t("Cash refunds");
    },

    pledgeReturnBankLabel() {
        return _t("Bank refunds");
    },

    pledgeReturnPaymentMethodLabel() {
        return _t("Return payment methods");
    },

    pledgeReturnPaymentMethodLineLabel(row) {
        const name = row?.payment_method_name || _t("Unknown");
        const count = row?.count || 0;
        return count > 1 ? `${name} (${count})` : name;
    },

    pledgeReturnPaymentMethods() {
        return this.props.pledge_completion_details?.return_by_payment_method || [];
    },

    shouldShowPledgeReturnPaymentMethods() {
        return this.pledgeReturnPaymentMethods().length > 0;
    },

    shouldShowPledgeClosingSection() {
        const details = this.props.pledge_completion_details;
        if (!details) {
            return false;
        }
        return !!(details.collected_count || details.returned_count);
    },

    shouldShowPledgeCollectedBlock() {
        const details = this.props.pledge_completion_details;
        return !!(details && details.collected_count);
    },

    shouldShowPledgeReturnedBlock() {
        const details = this.props.pledge_completion_details;
        return !!(details && details.returned_count);
    },
});
