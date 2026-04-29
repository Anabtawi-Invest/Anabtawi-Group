/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export class AdvanceOrderFormPopup extends Component {
    static template = "pos_advance_order.AdvanceOrderFormPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        posConfigId: { type: Number, optional: true },
        companyId: { type: Number, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            advance_amount: 0,
            payment_method: "cash",
            pos_config_id: this.props.posConfigId || null,
            pos_config_name: "",
            pos_config_pricelist: null,
            pricelist_name: "",
            with_employee: false,
            employee_id: null,
            discount_id: null,
            employees: [],
            discounts: [],
        });

        onMounted(async () => {
            await this._loadPopupData();
            this.state.loading = false;
        });
    }

    async _loadPopupData() {
        const companyId = this.props.companyId || false;
        const employeeDomain = companyId
            ? ["|", ["company_id", "=", false], ["company_id", "=", companyId]]
            : [];
        const discountDomain = [["active", "=", true]];
        if (companyId) {
            discountDomain.push(["company_id", "=", companyId]);
        }
        try {
            const [employees, discounts, posConfig] = await Promise.all([
                this.orm.searchRead("hr.employee", employeeDomain, ["id", "name"], { limit: 200 }),
                this.orm.searchRead(
                    "pos.advance.discount",
                    discountDomain,
                    ["id", "name", "discount_type", "value"],
                    { limit: 200 }
                ),
                this.orm.read("pos.config", [this.props.posConfigId], ["id", "name", "pricelist_id"]),
            ]);
            this.state.employees = employees || [];
            this.state.discounts = discounts || [];
            const currentConfig = (posConfig || [])[0];
            this.state.pos_config_id = currentConfig?.id || this.props.posConfigId || null;
            this.state.pos_config_name = currentConfig?.name || "";
            this.state.pos_config_pricelist = currentConfig?.pricelist_id || null;
            this._syncPricelistName();
        } catch (error) {
            this.notification.add(
                error?.message || _t("Failed to load popup data."),
                { type: "danger" }
            );
        }
    }

    _syncPricelistName() {
        this.state.pricelist_name = this.state.pos_config_pricelist?.[1] || "";
    }

    onAdvanceAmountInput(ev) {
        const value = Number(ev.target.value || 0);
        this.state.advance_amount = Number.isFinite(value) ? value : 0;
    }

    onPaymentMethodChange(ev) {
        this.state.payment_method = ev.target.value || "cash";
    }

    onWithEmployeeChange(ev) {
        this.state.with_employee = !!ev.target.checked;
        if (!this.state.with_employee) {
            this.state.employee_id = null;
        }
    }

    onEmployeeChange(ev) {
        this.state.employee_id = ev.target.value ? parseInt(ev.target.value, 10) : null;
    }

    onDiscountChange(ev) {
        this.state.discount_id = ev.target.value ? parseInt(ev.target.value, 10) : null;
    }

    get discountLabelSuffix() {
        return (discount) =>
            discount.discount_type === "percent"
                ? `${discount.value}%`
                : `${discount.value}`;
    }

    confirm() {
        if (!this.state.advance_amount || this.state.advance_amount <= 0) {
            this.notification.add(_t("Advance amount must be greater than zero."), { type: "warning" });
            return;
        }
        if (!this.state.pos_config_id) {
            this.notification.add(_t("Current POS configuration is missing."), { type: "warning" });
            return;
        }
        if (this.state.with_employee && !this.state.employee_id) {
            this.notification.add(_t("Please select an employee."), { type: "warning" });
            return;
        }
        this.props.getPayload({
            advance_amount: this.state.advance_amount,
            payment_method: this.state.payment_method,
            pos_config_id: this.state.pos_config_id,
            employee_id: this.state.with_employee ? this.state.employee_id : false,
            discount_id: this.state.discount_id || false,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}

