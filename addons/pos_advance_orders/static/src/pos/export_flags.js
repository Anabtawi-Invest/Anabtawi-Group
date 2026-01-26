/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order, Orderline } from "@point_of_sale/app/store/models";

patch(Order.prototype, {
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.advance_order_id = this.advance_order_id || false;
        json.customer_mobile =
            this.customer_mobile ||
            (this.get_partner() ? (this.get_partner().mobile || this.get_partner().phone || false) : false);
        return json;
    },
});

patch(Orderline.prototype, {
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.is_pledge_line = !!this.is_pledge_line;
        json.is_advance_deposit_line = !!this.is_advance_deposit_line;
        json.pledge_origin_product_id = this.pledge_origin_product_id || false;
        return json;
    },
});
