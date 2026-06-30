/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { formatCurrency } from "@web/core/currency";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";

function isCapDiscountOrder(line) {
    return Boolean(line.order_id?.pricelist_id?.cap_enabled);
}

patch(Orderline.prototype, {
    get lineScreenValues() {
        const vals = super.lineScreenValues;
        const line = this.line;

        if (!vals || Object.keys(vals).length === 0 || !isCapDiscountOrder(line)) {
            return vals;
        }

        const hasDiscount = line.getDiscount() > 0 && !line.combo_parent_id;
        const result = {
            ...vals,
            discount: false,
        };

        if (!hasDiscount || this.props.basic_receipt) {
            return result;
        }

        const originalPrice = formatCurrency(line.displayPriceUnitNoDiscount, line.currency.id);
        const finalPrice = formatCurrency(line.displayPriceUnit, line.currency.id);
        const originalLabel = vals.isReceipt ? _t("Original Price") : _t("Original Unit Price");
        const finalLabel = vals.isReceipt ? _t("Final Price") : _t("Final Unit Price");

        return {
            ...result,
            displayPriceUnit: `${originalLabel}: ${originalPrice} | ${finalLabel}: ${finalPrice}`,
        };
    },
});
