/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class PredefinedDiscountAuthPopup extends Component {
    static template = "pos_predefined_discounts.PredefinedDiscountAuthPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        discounts: { type: Array, optional: true },
        employees: { type: Array, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Discount Authorization"),
        discounts: [],
        employees: [],
    };

    setup() {
        this.state = useState({
            discountId: this.props.discounts?.[0]?.id || null,
            isEmployee: false,
            employeeId: this.props.employees?.[0]?.id || null,
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

    get selectedDiscount() {
        return this.props.discounts.find((discount) => discount.id === this.state.discountId);
    }

    get filteredEmployees() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (!q) {
            return this.props.employees;
        }
        return this.props.employees.filter((employee) => {
            const name = (employee.name || "").toLowerCase();
            const barcode = (employee.barcode || "").toLowerCase();
            return name.includes(q) || barcode.includes(q);
        });
    }

    get showEmployeeOptions() {
        return Boolean(this.selectedDiscount?.is_employee_discount);
    }

    get showEmployeeField() {
        return this.showEmployeeOptions && this.state.isEmployee;
    }

    get canConfirm() {
        return Boolean(
            this.state.discountId &&
            (this.state.password || "").trim() &&
            (!this.showEmployeeField || this.state.employeeId)
        );
    }

    onDiscountChange(ev) {
        this.state.discountId = ev.target.value ? parseInt(ev.target.value, 10) : null;
        if (!this.showEmployeeOptions) {
            this.state.isEmployee = false;
        }
    }

    onIsEmployeeChange(ev) {
        this.state.isEmployee = !!ev.target.checked;
    }

    confirm() {
        if (!this.canConfirm) {
            return;
        }
        this.props.getPayload({
            discountId: this.state.discountId,
            employeeId: this.showEmployeeField ? this.state.employeeId : false,
            password: this.state.password,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
