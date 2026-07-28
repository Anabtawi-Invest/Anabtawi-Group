/** @odoo-module **/

import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { patch } from "@web/core/utils/patch";
import { debounce } from "@web/core/utils/timing";
import { useEffect } from "@odoo/owl";

patch(PartnerList.prototype, {
    setup() {
        super.setup(...arguments);
        this.debouncedServerSearch = debounce(() => this._serverSearchIfNeeded(), 400);
        useEffect(
            () => {
                this.debouncedServerSearch();
            },
            () => [this.state.query]
        );
    },

    _getSearchFields(query) {
        const stripped = (query || "").replace(/[+\s()\-./]/g, "");
        if (/^\d+$/.test(stripped) && stripped.length >= 3) {
            return ["employee_number", "phone_mobile_search", "barcode", "vat", "zip"];
        }
        const fields = super._getSearchFields(query);
        if (query && !fields.includes("employee_number")) {
            fields.push("employee_number");
        }
        return fields;
    },

    async _serverSearchIfNeeded() {
        const query = this.state.query?.trim();
        if (!query || this.state.loading) {
            return;
        }
        const localMatches =
            this.getPartners(this.state.initialPartners).length +
            this.getPartners(this.state.loadedPartners).length;
        if (localMatches === 0) {
            await this.getNewPartners();
        }
    },
});
