/** @odoo-module **/

import { OpeningControlPopup } from "@point_of_sale/app/components/popups/opening_control_popup/opening_control_popup";
import { patch } from "@web/core/utils/patch";
import { onWillStart } from "@odoo/owl";

patch(OpeningControlPopup.prototype, {
    setup() {
        super.setup(...arguments);
        onWillStart(async () => {
            await this.pos.data.call(
                "pos.session",
                "pos_opening_cash_zero_reset",
                [[this.pos.session.id]]
            );
            this.state.openingCash = this.env.utils.formatCurrency(0, false);
            this.pos.session.cash_register_balance_start = 0;
        });
    },
});
