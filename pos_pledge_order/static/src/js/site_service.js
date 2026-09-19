/** @odoo-module */

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

/**
 * Site / Cutting service lines on regular POS payment:
 * - After the service-type popup, On Site / Cutting adds the matching product
 *   using the price from the On-Site Prices range that matches qty × multiple.
 * - Advance Order uses the same helpers in pos_advance_order
 *   (see appendSiteServiceLineIfNeeded).
 */
patch(PosOrderline.prototype, {
    setup(vals) {
        super.setup(vals);
        this.is_site_service_auto = vals?.is_site_service_auto || false;
    },
});
