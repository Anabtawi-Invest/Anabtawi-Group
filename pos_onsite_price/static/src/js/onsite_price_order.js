/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.is_onsite_order = Boolean(vals?.is_onsite_order);
        this.onsite_pricing_is_on_site = Boolean(
            vals?.onsite_pricing_is_on_site ?? vals?.is_onsite_order
        );
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        data.is_onsite_order = Boolean(this.is_onsite_order || this.onsite_pricing_is_on_site);
        return data;
    },
});
