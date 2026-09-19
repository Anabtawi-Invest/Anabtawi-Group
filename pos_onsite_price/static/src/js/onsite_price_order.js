/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { getOrderServiceType, SERVICE_TYPE } from "@pos_onsite_price/js/onsite_price_utils";

patch(PosOrder.prototype, {
    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        const serviceType = getOrderServiceType(this);
        if (this.model?.fields?.is_onsite_order) {
            data.is_onsite_order =
                serviceType === SERVICE_TYPE.ON_SITE || serviceType === SERVICE_TYPE.CUTTING;
        }
        if (this.model?.fields?.onsite_service_type) {
            data.onsite_service_type = serviceType;
        }
        return data;
    },
});
