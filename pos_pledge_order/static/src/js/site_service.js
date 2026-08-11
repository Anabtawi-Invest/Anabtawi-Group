/** @odoo-module */

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

/**
 * Site Service is never auto-added on regular POS payment.
 * It is only applied when the cashier explicitly enables it while creating
 * an Advance Order (pos_advance_order + site_service_utils.js).
 */
patch(PosOrderline.prototype, {
    setup(vals) {
        super.setup(vals);
        this.is_site_service_auto = vals?.is_site_service_auto || false;
    },
});
