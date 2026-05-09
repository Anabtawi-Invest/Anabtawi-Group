/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { clearGettersCache } from "@point_of_sale/lazy_getter";
import { PosOrderlineAccounting } from "@point_of_sale/app/models/accounting/pos_order_line_accounting";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

/**
 * Core POS assumes `orderLine.order_id` is always set. After sync / related-model
 * updates, some lines can briefly lack `order_id`, breaking receipt rendering.
 *
 * Lazy getters are cached: patch then `clearGettersCache()`.
 */
function pledgeLogReceiptGuard(source, message, payload) {
    console.warn("[pos_pledge_order][receipt_guard]", source, message, {
        ...payload,
        ts: new Date().toISOString(),
    });
}

patch(PosOrderlineAccounting.prototype, {
    get taxGroupLabels() {
        try {
            let taxes_id = this.tax_ids;
            const order = this.order_id;

            if (!order) {
                pledgeLogReceiptGuard("taxGroupLabels", "order_id missing", {
                    lineUuid: this.uuid,
                    lineBackendId: typeof this.id === "number" ? this.id : undefined,
                    productId: this.product_id?.id,
                    model: this.constructor?.name,
                });
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
            pledgeLogReceiptGuard("taxGroupLabels", "exception", {
                error: String(error),
                lineUuid: this.uuid,
                productId: this.product_id?.id,
            });
            return "";
        }
    },
});

patch(PosOrderline.prototype, {
    get currency() {
        return this.order_id?.currency || this.config?.currency_id;
    },
});

patch(PosOrder.prototype, {
    getTotalDiscount() {
        const ignored_product_ids = this._getIgnoredProductIdsTotalDiscount();
        return this.currency.round(
            this.lines.reduce((sum, orderLine) => {
                const ord = orderLine.order_id;
                if (!ord?.prices?.baseLineByLineUuids) {
                    if (!ord) {
                        pledgeLogReceiptGuard("getTotalDiscount", "line without order_id", {
                            lineUuid: orderLine.uuid,
                        });
                    }
                    return sum;
                }
                if (orderLine.product_id && ignored_product_ids.includes(orderLine.product_id.id)) {
                    return sum;
                }
                const data = ord.prices.baseLineByLineUuids[orderLine.uuid];
                if (!data?.tax_details) {
                    return sum;
                }
                sum += data.tax_details.discount_amount || 0;
                if (
                    orderLine.displayDiscountPolicy() === "without_discount" &&
                    !(orderLine.price_type === "manual") &&
                    orderLine.discount == 0
                ) {
                    sum +=
                        (orderLine.displayPriceUnit - orderLine.displayPriceUnitNoDiscount) *
                        orderLine.getQuantity();
                }
                return sum;
            }, 0)
        );
    },
});

clearGettersCache();
