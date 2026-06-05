/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { UrlOrdersPopup } from "@pos_self_order_location/pos/components/url_orders_popup/url_orders_popup";

patch(ControlButtons.prototype, {
    async clickUrlOrdersButton() {
        this.dialog.add(UrlOrdersPopup, {});
    },
});
