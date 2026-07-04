/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class EmployeePasswordPopup extends Component {
    static template = "employee_request.EmployeePasswordPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        employees: { type: Array, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Employee Authorization"),
        employees: [],
    };

    setup() {
        this.state = useState({
            employeeId: this.props.employees?.[0]?.id || null,
            password: "",
            search: "",
        });
        this.passwordRef = useRef("password");
        onMounted(() => this.passwordRef.el?.focus?.());
    }

    get filteredEmployees() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (!q) {
            return this.props.employees;
        }
        return this.props.employees.filter((e) => {
            const name = (e.name || "").toLowerCase();
            const barcode = (e.barcode || "").toLowerCase();
            return name.includes(q) || barcode.includes(q);
        });
    }

    get canConfirm() {
        return Boolean(this.state.employeeId) && Boolean((this.state.password || "").trim());
    }

    confirm() {
        if (!this.canConfirm) {
            return;
        }
        this.props.getPayload({
            employeeId: this.state.employeeId,
            password: this.state.password,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}

