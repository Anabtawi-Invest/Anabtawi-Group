/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        if (this.model?.fields?.is_onsite_order) {
            data.is_onsite_order = Boolean(
                this.is_onsite_order || this.uiState?.onsitePricing?.isOnSite
            );
        }
        return data;
    },
});
