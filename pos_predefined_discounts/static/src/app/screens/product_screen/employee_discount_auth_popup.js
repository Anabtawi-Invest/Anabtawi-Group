/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class EmployeeDiscountAuthPopup extends Component {
    static template = "pos_predefined_discounts.EmployeeDiscountAuthPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        discounts: { type: Array, optional: true },
        partners: { type: Array, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Employee Discount"),
        discounts: [],
        partners: [],
    };

    setup() {
        this.state = useState({
            discountId: this.props.discounts?.[0]?.id || null,
            partnerId: this.props.partners?.[0]?.id || null,
            password: "",
            search: "",
        });
        this.passwordRef = useRef("password");
        onMounted(() => {
            this.state.password = "";
            if (this.passwordRef.el) {
                this.passwordRef.el.value = "";
                this.passwordRef.el.focus?.();
            }
        });
    }

    get filteredPartners() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (!q) {
            return this.props.partners;
        }
        return this.props.partners.filter((partner) => {
            const name = (partner.name || "").toLowerCase();
            const barcode = (partner.barcode || "").toLowerCase();
            return name.includes(q) || barcode.includes(q);
        });
    }

    get canConfirm() {
        return Boolean(
            this.state.discountId &&
                this.state.partnerId &&
                (this.state.password || "").trim()
        );
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
