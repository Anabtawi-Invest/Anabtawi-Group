/** @odoo-module */

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

/**
 * Site Service is NOT applied automatically on regular POS sales or at payment.
 *
 * - Direct Payment (with or without pledge mapping): no Site Service line.
 * - Advance Order: Site Service is added only when the cashier enables the
 *   "Site Service" checkbox in the Advance popup (see pos_advance_order).
 */
patch(PosOrderline.prototype, {
    setup(vals) {
        super.setup(vals);
        this.is_site_service_auto = vals?.is_site_service_auto || false;
    },
});
