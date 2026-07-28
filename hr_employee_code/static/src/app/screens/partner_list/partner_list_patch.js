/** @odoo-module **/

import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { patch } from "@web/core/utils/patch";
import { debounce } from "@web/core/utils/timing";
import { useEffect } from "@odoo/owl";
import { normalize } from "@web/core/l10n/utils";

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
        if (/^\d+$/.test(stripped)) {
            return ["employee_number", "phone_mobile_search", "barcode", "vat", "zip"];
        }
        const fields = super._getSearchFields(query);
        if (query && !fields.includes("employee_number")) {
            fields.push("employee_number");
        }
        return fields;
    },

    getPartners(partners) {
        const searchWord = normalize(this.state.query?.trim() ?? "");
        const stripped = searchWord.replace(/[+\s()\-./]/g, "");
        if (searchWord && /^\d+$/.test(stripped)) {
            const allPartners = [...this.state.initialPartners, ...this.state.loadedPartners];
            const hasExactEmployee = allPartners.some(
                (partner) =>
                    partner.employee_number &&
                    normalize(partner.employee_number) === searchWord
            );
            if (hasExactEmployee) {
                return partners.filter(
                    (partner) =>
                        partner.employee_number &&
                        normalize(partner.employee_number) === searchWord
                );
            }
        }
        return super.getPartners(partners);
    },

    async _serverSearchIfNeeded() {
        const query = this.state.query?.trim();
        if (!query || this.state.loading) {
            return;
        }
        const stripped = query.replace(/[+\s()\-./]/g, "");
        const isNumeric = /^\d+$/.test(stripped);
        const localMatches =
            this.getPartners(this.state.initialPartners).length +
            this.getPartners(this.state.loadedPartners).length;

        if (localMatches === 0 || isNumeric) {
            await this.getNewPartners();
        }
    },
});
