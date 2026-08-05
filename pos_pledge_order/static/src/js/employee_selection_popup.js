/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class EmployeeSelectionPopup extends Component {
    static template = "pos_pledge.EmployeeSelectionPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.pos = usePos();

        this.state = useState({
            employees: [],
            selectedEmployee: null,
            search: "",
        });

        onMounted(() => this._loadEmployees());
    }

    async _loadEmployees() {
        console.log("[PLEDGE] Loading employees for popup...");
        try {
            this.state.employees = await this.orm.searchRead(
                "hr.employee",
                [['active', '=', true]],
                ['id', 'name', 'work_phone', 'work_email', 'job_title'],
                { order: 'name asc' }
            );
            console.log("[PLEDGE] Loaded", this.state.employees.length, "employees");
        } catch (error) {
            console.error("[PLEDGE] Error loading employees:", error);
            this.notification.add(
                _t("Failed to load employees"),
                { type: "danger" }
            );
        }
    }

    onSearchInput(ev) {
        this.state.search = (ev.target.value || "").toLowerCase();
        console.log("[PLEDGE] Search updated:", this.state.search);
    }

    get filteredEmployees() {
        if (!this.state.search) {
            return this.state.employees;
        }

        return this.state.employees.filter(employee =>
            employee.name?.toLowerCase().includes(this.state.search) ||
            (employee.job_title && (
                (Array.isArray(employee.job_title) && employee.job_title[1]?.toLowerCase().includes(this.state.search)) ||
                (typeof employee.job_title === 'string' && employee.job_title.toLowerCase().includes(this.state.search))
            ))
        );
    }

    onSearchKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }

        ev.preventDefault();

        if (!this.filteredEmployees.length) {
            this.notification.add(
                _t("No employee found."),
                { type: "warning" }
            );
            return;
        }

        const first = this.filteredEmployees[0];
        console.log("[PLEDGE] Enter pressed, selecting first employee:", first);
        this.selectEmployee(first);
    }

    selectEmployee(employee) {
        console.log("[PLEDGE] Employee selected:", employee);
        this.props.getPayload(employee);
        this.props.close();
    }

    cancel() {
        console.log("[PLEDGE] Employee selection cancelled");
        this.props.getPayload(null);
        this.props.close();
    }
}
