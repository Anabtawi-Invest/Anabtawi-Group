/** @odoo-module **/

import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

// Extend ClosePosPopup.props in OWL 2 to accept advance deposit/refund details and any custom props
if (ClosePosPopup.props) {
    ClosePosPopup.props = {
        ...ClosePosPopup.props,
        advance_deposit_details: { type: [Object, Boolean, String], optional: true },
        advance_refund_details: { type: [Object, Boolean, String], optional: true },
        default_cash_details: { type: [Object, Boolean, String], optional: true },
        "*": true,
    };
}
