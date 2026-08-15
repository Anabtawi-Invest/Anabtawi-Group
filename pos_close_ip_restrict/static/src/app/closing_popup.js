/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import { closeDeviceContext } from "@pos_close_ip_restrict/app/close_device_token";

const CLOSE_METHODS = new Set([
    "post_closing_cash_details",
    "update_closing_control_state_session",
    "close_session_from_ui",
    "check_close_allowed_ip",
]);

patch(ClosePosPopup.prototype, {
    async closeSession() {
        const data = this.pos.data;
        const originalCall = data.call.bind(data);
        data.call = (model, method, args, kwargs = {}) => {
            if (model === "pos.session" && CLOSE_METHODS.has(method)) {
                kwargs = {
                    ...kwargs,
                    context: closeDeviceContext(kwargs.context || {}),
                };
            }
            return originalCall(model, method, args, kwargs);
        };
        try {
            return await super.closeSession(...arguments);
        } finally {
            data.call = originalCall;
        }
    },
});
