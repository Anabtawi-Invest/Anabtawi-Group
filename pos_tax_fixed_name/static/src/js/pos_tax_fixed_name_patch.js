/** @odoo-module **/

import { PosOrderAccounting } from "@point_of_sale/app/models/accounting/pos_order_accounting";
import { patch } from "@web/core/utils/patch";

patch(PosOrderAccounting.prototype, {
    _computeAllPrices(opts = {}) {
        const result = super._computeAllPrices(opts);
        const fixedNamesByTaxGroup = {};

        for (const tax of this.models["account.tax"].getAll()) {
            const fixedName = (tax.pos_fixed_name || "").trim();
            if (fixedName && tax.tax_group_id?.id) {
                fixedNamesByTaxGroup[tax.tax_group_id.id] = fixedName;
            }
        }

        for (const subtotal of result.taxDetails?.subtotals || []) {
            for (const taxGroup of subtotal.tax_groups || []) {
                const fixedName = fixedNamesByTaxGroup[taxGroup.id];
                if (fixedName) {
                    taxGroup.group_name = fixedName;
                    taxGroup.group_label = "";
                }
            }
        }

        return result;
    },
});
