/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { clearGettersCache } from "@point_of_sale/lazy_getter";
import { PosOrderlineAccounting } from "@point_of_sale/app/models/accounting/pos_order_line_accounting";

/**
 * Core `taxGroupLabels` does `this.order_id.fiscal_position_id` with no guard.
 * Some receipt/sync paths expose lines with no `order_id`, which throws.
 *
 * POS caches lazy getters on first use; patching only `PosOrderline.prototype`
 * can be ignored if that cache was built earlier — patch the accounting class
 * where the getter is defined and invalidate the cache.
 */
function pledgeLogTaxGroupLabels(level, message, payload) {
    const prefix = "[pos_pledge_order][taxGroupLabels]";
    const entry = { message, ...payload, ts: new Date().toISOString() };
    if (level === "error") {
        console.error(prefix, entry);
    } else {
        console.warn(prefix, entry);
    }
}

patch(PosOrderlineAccounting.prototype, {
    get taxGroupLabels() {
        try {
            let taxes_id = this.tax_ids;
            const order = this.order_id;

            if (!order) {
                pledgeLogTaxGroupLabels("warn", "order_id is missing on line when reading taxGroupLabels", {
                    lineUuid: this.uuid,
                    lineBackendId: typeof this.id === "number" ? this.id : undefined,
                    productId: this.product_id?.id,
                    model: this.constructor?.name,
                });
            } else if (!order.fiscal_position_id) {
                // no log — normal when no fiscal position on order
            }

            if (order?.fiscal_position_id) {
                taxes_id = order.fiscal_position_id.getTaxesAfterFiscalPosition(this.tax_ids);
            }
            return [
                ...new Set(
                    taxes_id
                        ?.map((tax) => tax.tax_group_id?.pos_receipt_label)
                        .filter((label) => label)
                ),
            ].join(" ");
        } catch (error) {
            pledgeLogTaxGroupLabels("error", "taxGroupLabels threw", {
                error: String(error),
                lineUuid: this.uuid,
                lineBackendId: typeof this.id === "number" ? this.id : undefined,
                productId: this.product_id?.id,
                model: this.constructor?.name,
            });
            return "";
        }
    },
});

clearGettersCache();
