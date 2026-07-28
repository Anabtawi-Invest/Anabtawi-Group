/** @odoo-module **/

import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { patch } from "@web/core/utils/patch";

patch(PartnerList.prototype, {
    _getSearchFields(query) {
        const fields = super._getSearchFields(query);
        if (query && !fields.includes("employee_number")) {
            fields.push("employee_number");
        }
        return fields;
    },
});
