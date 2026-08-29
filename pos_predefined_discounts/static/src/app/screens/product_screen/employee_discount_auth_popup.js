/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";

export class EmployeeDiscountAuthPopup extends Component {
    static template = "pos_predefined_discounts.EmployeeDiscountAuthPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        discounts: { type: Array, optional: true },
        partners: { type: Array, optional: true },
        configId: { type: Number, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Employee Discount"),
        discounts: [],
        partners: [],
        configId: false,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            discountId: this.props.discounts?.[0]?.id || null,
            partnerId: this.props.partners?.[0]?.id || null,
            password: "",
            search: "",
            partners: [...(this.props.partners || [])],
            loading: false,
        });
        this.passwordRef = useRef("password");
        this._debouncedSearch = debounce(this._searchPartners.bind(this), 300);
        onMounted(() => {
            this.state.password = "";
            if (this.passwordRef.el) {
                this.passwordRef.el.value = "";
                this.passwordRef.el.focus?.();
            }
        });
    }

    get canConfirm() {
        return Boolean(
            this.state.discountId &&
                this.state.partnerId &&
                (this.state.password || "").trim()
        );
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value || "";
        this._debouncedSearch();
    }

    async _searchPartners() {
        if (!this.props.configId) {
            return;
        }
        this.state.loading = true;
        try {
            const partners = await this.orm.call(
                "pos.predefined.discount",
                "pos_get_employee_partners",
                [this.props.configId, this.state.search, 200]
            );
            this.state.partners = partners || [];
            if (
                this.state.partnerId &&
                !this.state.partners.some((partner) => partner.id === this.state.partnerId)
            ) {
                this.state.partnerId = this.state.partners[0]?.id || null;
            }
            if (!this.state.partnerId && this.state.partners.length) {
                this.state.partnerId = this.state.partners[0].id;
            }
        } catch {
            // Keep current list on search failure.
        } finally {
            this.state.loading = false;
        }
    }

    confirm() {
        if (!this.canConfirm) {
            return;
        }
        this.props.getPayload({
            discountId: this.state.discountId,
            partnerId: this.state.partnerId,
            password: this.state.password,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
