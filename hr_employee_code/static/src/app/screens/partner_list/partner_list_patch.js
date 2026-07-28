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
        searchString: partner.searchString,
    };
}

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
        let fields;
        if (/^\d+$/.test(stripped)) {
            fields = ["employee_number", "phone_mobile_search", "barcode", "vat", "zip"];
        } else {
            fields = super._getSearchFields(query);
            if (query && !fields.includes("employee_number")) {
                fields.push("employee_number");
            }
        }
        console.info(LOG_PREFIX, "_getSearchFields", { query, stripped, fields });
        return fields;
    },

    getPartners(partners) {
        const searchWord = normalize(this.state.query?.trim() ?? "");
        const stripped = searchWord.replace(/[+\s()\-./]/g, "");
        let result;
        if (searchWord && /^\d+$/.test(stripped)) {
            const allPartners = [...this.state.initialPartners, ...this.state.loadedPartners];
            const exactEmployeePartners = allPartners.filter(
                (partner) =>
                    partner.employee_number &&
                    normalize(partner.employee_number) === searchWord
            );
            const hasExactEmployee = exactEmployeePartners.length > 0;
            console.info(LOG_PREFIX, "getPartners numeric", {
                searchWord,
                poolSize: partners.length,
                allPartnersCount: allPartners.length,
                exactEmployeePartners: exactEmployeePartners.map(partnerSummary),
                hasExactEmployee,
            });
            if (hasExactEmployee) {
                result = partners.filter(
                    (partner) =>
                        partner.employee_number &&
                        normalize(partner.employee_number) === searchWord
                );
            } else {
                result = super.getPartners(partners);
            }
        } else {
            result = super.getPartners(partners);
        }
        console.info(LOG_PREFIX, "getPartners result", {
            searchWord,
            inputPool: partners.length,
            resultCount: result.length,
            results: result.slice(0, 10).map(partnerSummary),
        });
        return result;
    },

    async _serverSearchIfNeeded() {
        const query = this.state.query?.trim();
        if (!query || this.state.loading) {
            console.info(LOG_PREFIX, "_serverSearchIfNeeded skipped", {
                query,
                loading: this.state.loading,
            });
            return;
        }
        const stripped = query.replace(/[+\s()\-./]/g, "");
        const isNumeric = /^\d+$/.test(stripped);
        const initialMatches = this.getPartners(this.state.initialPartners);
        const loadedMatches = this.getPartners(this.state.loadedPartners);
        const localMatches = initialMatches.length + loadedMatches.length;

        console.info(LOG_PREFIX, "_serverSearchIfNeeded", {
            query,
            isNumeric,
            localMatches,
            posCompanyId: this.pos?.company?.id,
            posCompanyName: this.pos?.company?.name,
            configId: this.pos?.config?.id,
        });

        if (localMatches === 0 || isNumeric) {
            await this.getNewPartners();
        }
    },

    async getNewPartners() {
        let domain = [];
        const offset = this.globalState.offsetBySearch[this.state.query] || 0;
        if (offset > this.loadedPartnerIds.size) {
            console.info(LOG_PREFIX, "getNewPartners skipped offset", {
                query: this.state.query,
                offset,
                loadedPartnerIdsSize: this.loadedPartnerIds.size,
            });
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
                count: partners.length,
                partners: partners.map((p) => ({
                    id: p.id,
                    name: p.name,
                    employee_number: p.employee_number,
                })),
            });

            this.globalState.offsetBySearch[this.state.query] =
                offset + (partners.length || 100);

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
        console.info(LOG_PREFIX, "searchPartner Enter pressed", { query: this.state.query });
        const partners = await this.getNewPartners();
        console.info(LOG_PREFIX, "searchPartner done", {
            query: this.state.query,
            count: partners.length,
        });
        return partners;
    },
});
