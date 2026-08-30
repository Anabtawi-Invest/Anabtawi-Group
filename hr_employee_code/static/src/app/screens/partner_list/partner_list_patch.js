/** @odoo-module **/

import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { patch } from "@web/core/utils/patch";
import { debounce } from "@web/core/utils/timing";
import { useEffect } from "@odoo/owl";
import { normalize } from "@web/core/l10n/utils";

const LOG_PREFIX = "[hr_employee_code POS]";

function partnerSummary(partner) {
    return {
        id: partner.id,
        name: partner.name,
        employee_number: partner.employee_number,
        phone: partner.phone,
    };
}

patch(PartnerList.prototype, {
    setup() {
        super.setup(...arguments);
        this._resetPartnerSearchOffset = false;
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
            const exactEmployeePartners = allPartners.filter(
                (partner) =>
                    partner.employee_number &&
                    normalize(partner.employee_number) === searchWord
            );
            if (exactEmployeePartners.length) {
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

        console.info(LOG_PREFIX, "_serverSearchIfNeeded", {
            query,
            isNumeric,
            localMatches,
            posCompanyId: this.pos?.company?.id,
        });

        if (localMatches === 0 || isNumeric) {
            this._resetPartnerSearchOffset = true;
            await this.getNewPartners();
        }
    },

    async getNewPartners() {
        let domain = [];
        let offset = this.globalState.offsetBySearch[this.state.query] || 0;
        if (this._resetPartnerSearchOffset) {
            offset = 0;
            this.globalState.offsetBySearch[this.state.query] = 0;
            this._resetPartnerSearchOffset = false;
        }
        if (offset > this.loadedPartnerIds.size) {
            console.info(LOG_PREFIX, "getNewPartners skipped", { query: this.state.query, offset });
            return [];
        }
        if (this.state.query) {
            const search_fields = this._getSearchFields(this.state.query);
            domain = [
                ...Array(search_fields.length - 1).fill("|"),
                ...search_fields.map((field) => [field, "ilike", this.state.query]),
            ];
        }

        console.info(LOG_PREFIX, "getNewPartners request", {
            query: this.state.query,
            offset,
            domain,
            configId: this.pos.config.id,
        });

        try {
            this.state.loading = true;
            const result = await this.pos.data.callRelated("res.partner", "get_new_partner", [
                this.pos.config.id,
                domain,
                offset,
            ]);

            const partners = result["res.partner"] || [];
            console.info(LOG_PREFIX, "getNewPartners response", {
                query: this.state.query,
                offset,
                count: partners.length,
                partners: partners.map((p) => ({
                    id: p.id,
                    name: p.name,
                    employee_number: p.employee_number,
                })),
            });

            if (partners.length) {
                this.globalState.offsetBySearch[this.state.query] = offset + partners.length;
            }

            for (const partner of partners) {
                if (!this.loadedPartnerIds.has(partner.id)) {
                    this.loadedPartnerIds.add(partner.id);
                    this.state.loadedPartners.push(partner);
                }
            }

            return partners;
        } catch (error) {
            console.error(LOG_PREFIX, "getNewPartners error", error);
            return [];
        } finally {
            this.state.loading = false;
        }
    },

    async searchPartner() {
        this._resetPartnerSearchOffset = true;
        console.info(LOG_PREFIX, "searchPartner Enter", { query: this.state.query });
        return this.getNewPartners();
    },
});
