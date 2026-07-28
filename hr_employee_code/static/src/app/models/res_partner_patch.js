/** @odoo-module **/

import { ResPartner } from "@point_of_sale/app/models/res_partner";
import { patch } from "@web/core/utils/patch";

patch(ResPartner.prototype, {
    get searchString() {
        const baseSearch = super.searchString;
        if (this.employee_number) {
            return `${baseSearch} ${this.employee_number}`.trim();
        }
        return baseSearch;
    },

    exactMatch(searchWord) {
        if (
            this.employee_number &&
            this.employee_number.toLowerCase() === searchWord.toLowerCase()
        ) {
            return true;
        }
        return super.exactMatch(searchWord);
    },
});
