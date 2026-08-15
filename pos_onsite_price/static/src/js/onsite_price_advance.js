/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { AdvanceOrderFormPopup } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/advance_order_form_popup";
import { promptAndApplyOnsitePricing, isOrderOnSite } from "@pos_onsite_price/js/onsite_price_utils";

patch(ControlButtons.prototype, {
    async onClickAdvanceOrder() {
        const result = await promptAndApplyOnsitePricing({
            pos: this.pos,
            dialog: this.dialog,
            notification: this.notification,
            stayMessage: _t("On-site prices applied. Continue with the advance order."),
        });
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
        const isOnSite = isOrderOnSite(order);
        this.state.site_service = isOnSite;
        if (isOnSite) {
            this.state.site_service_available = true;
        }
        return super.confirm(...arguments);
    },
});
