/** @odoo-module */

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

/**
 * Site Service on regular POS payment:
 * - After the on-site Yes/No popup, Yes adds the cutting service when score < threshold.
 * - Advance Order uses the same scoring via pos_advance_order (see appendSiteServiceLineIfNeeded).
 */
patch(PosOrderline.prototype, {
    setup(vals) {
        super.setup(vals);
        this.is_site_service_auto = vals?.is_site_service_auto || false;
    },
});
