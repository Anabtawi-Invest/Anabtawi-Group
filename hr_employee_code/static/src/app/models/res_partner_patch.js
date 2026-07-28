/** @odoo-module **/

import { ResPartner } from "@point_of_sale/app/models/res_partner";
import { patch } from "@web/core/utils/patch";

patch(ResPartner.prototype, {
    get searchString() {
        if (this._searchString) {
            if (this.employee_number && !this._searchString.includes(this.employee_number)) {
                return `${this._searchString} ${this.employee_number}`.trim();
            }
            return this._searchString;
        }

        const fields = [
            "name",
            "barcode",
            "phone",
            "email",
            "vat",
            "parent_name",
            "pos_contact_address",
            "employee_number",
        ];
        this._searchString = fields
            .map((field) => {
                if (field === "phone" && this[field]) {
                    return this[field].replace(/[+\s()-]/g, "");
                }
                return this[field] || "";
            })
            .filter(Boolean)
            .join(" ");
        return this._searchString;
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

    update(vals, opts) {
        const result = super.update(vals, opts);
        this._searchString = null;
        return result;
    },
});
