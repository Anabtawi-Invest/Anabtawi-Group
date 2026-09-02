/** @odoo-module **/

import { OpeningControlPopup } from "@point_of_sale/app/components/popups/opening_control_popup/opening_control_popup";
import { patch } from "@web/core/utils/patch";
import { onWillStart } from "@odoo/owl";

const _openingResetInFlight = new Map();

patch(OpeningControlPopup.prototype, {
    setup() {
        super.setup(...arguments);
        onWillStart(async () => {
            const sessionId = this.pos.session.id;
            if (!_openingResetInFlight.has(sessionId)) {
                const resetPromise = this.pos.data
                    .call("pos.session", "pos_opening_cash_zero_reset", [[sessionId]])
                    .finally(() => {
                        _openingResetInFlight.delete(sessionId);
                    });
                _openingResetInFlight.set(sessionId, resetPromise);
                await resetPromise;
            } else {
                await _openingResetInFlight.get(sessionId);
            }
            this.state.openingCash = this.env.utils.formatCurrency(0, false);
            this.pos.session.cash_register_balance_start = 0;
        });
    },
});
