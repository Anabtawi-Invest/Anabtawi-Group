/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { AdvanceOrderFormPopup } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/advance_order_form_popup";
import {
    promptAndApplyOnsitePricing,
    getOrderServiceType,
    getOnsiteUiState,
    logOnsite,
    SERVICE_TYPE,
} from "@pos_onsite_price/js/onsite_price_utils";

logOnsite("advance patch loaded");

patch(ControlButtons.prototype, {
    async onClickAdvanceOrder() {
        logOnsite("Advance Order clicked");
        const result = await promptAndApplyOnsitePricing({
            pos: this.pos,
            dialog: this.dialog,
            notification: this.notification,
            stayMessage: _t("On-site prices applied. Continue with the advance order."),
            source: "advance",
        });
        logOnsite("Advance Order after prompt", result);
        if (result?.cancelled || result?.error) {
            return;
        }
        return await super.onClickAdvanceOrder(...arguments);
    },
});

patch(AdvanceOrderFormPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.hideSiteServiceCheckbox = true;
    },

    confirm() {
        const order = this.props.pos.getOrder?.() || this.props.pos.get_order?.();
        const serviceType = getOrderServiceType(order);
        const state = getOnsiteUiState(order);
        // Both Site Service and Cutting skip pledges on the advance order.
        this.state.site_service =
            serviceType === SERVICE_TYPE.ON_SITE || serviceType === SERVICE_TYPE.CUTTING;
        if (this.state.site_service) {
            this.state.site_service_available = true;
        }
        this.state.onsite_service_type = serviceType;
        this.state.onsite_service_unit_price =
            serviceType === SERVICE_TYPE.CUTTING
                ? Number(state?.cuttingServicePrice || 0)
                : Number(state?.servicePrice || 0);
        return super.confirm(...arguments);
    },
});
