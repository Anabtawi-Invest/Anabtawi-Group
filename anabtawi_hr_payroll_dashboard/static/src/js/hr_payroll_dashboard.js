/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class HrPayrollDashboard extends Component {
    static template = "anabtawi_hr_payroll_dashboard.HrPayrollDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        const now = new Date();
        const firstDayThisMonth = new Date(now.getFullYear(), now.getMonth(), 1);
        const lastDayThisMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0);

        this.state = useState({
            period: "this_month",
            date_from: this._formatLocalDate(firstDayThisMonth),
            date_to: this._formatLocalDate(lastDayThisMonth),
            payrun_id: 0,
            company_id: 0,
            department_ids: [],
            searchQuery: "",
            sortKey: "net_salary",
            sortOrder: "desc",
            loading: true,
        });

        this.data = useState({
            date_from: "",
            date_to: "",
            selected_company_id: 0,
            selected_payrun_id: 0,
            payrun_batches: [],
            all_departments: [],
            all_companies: [],
            kpis: {},
            departments: [],
            channels: [],
            operational_highlights: {},
        });

        onWillStart(async () => {
            await this.fetchDashboardData();
        });
    }

    _formatLocalDate(dateObj) {
        if (!dateObj) return "";
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, "0");
        const day = String(dateObj.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    async fetchDashboardData() {
        this.state.loading = true;
        try {
            const res = await this.orm.call(
                "hr.payroll.dashboard",
                "get_dashboard_data",
                [],
                {
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    payrun_id: this.state.payrun_id,
                    company_id: this.state.company_id,
                    department_ids: this.state.department_ids,
                }
            );

            this.data.date_from = res.date_from || this.state.date_from;
            this.data.date_to = res.date_to || this.state.date_to;
            this.data.selected_company_id = res.selected_company_id;
            this.data.selected_payrun_id = res.selected_payrun_id;
            this.data.payrun_batches = res.payrun_batches || [];
            this.data.all_departments = res.all_departments || [];
            this.data.all_companies = res.all_companies || [];
            this.data.kpis = res.kpis || {};
            this.data.departments = res.departments || [];
            this.data.channels = res.channels || [];
            this.data.operational_highlights = res.operational_highlights || {};
        } catch (error) {
            console.error("Failed to load HR & Payroll dashboard data", error);
        } finally {
            this.state.loading = false;
        }
    }

    setPeriod(period) {
        this.state.period = period;
        const now = new Date();
        let fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
        let toDate = new Date(now.getFullYear(), now.getMonth() + 1, 0);

        if (period === "this_month") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
            toDate = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        } else if (period === "prev_month") {
            fromDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
            toDate = new Date(now.getFullYear(), now.getMonth(), 0);
        } else if (period === "this_quarter") {
            const quarterMonth = Math.floor(now.getMonth() / 3) * 3;
            fromDate = new Date(now.getFullYear(), quarterMonth, 1);
            toDate = new Date(now.getFullYear(), quarterMonth + 3, 0);
        } else if (period === "this_year") {
            fromDate = new Date(now.getFullYear(), 0, 1);
            toDate = new Date(now.getFullYear(), 11, 31);
        }

        this.state.date_from = this._formatLocalDate(fromDate);
        this.state.date_to = this._formatLocalDate(toDate);
        this.state.payrun_id = 0; // Reset batch selection when changing period
        this.fetchDashboardData();
    }

    onPayrunChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.payrun_id = val;
        this.fetchDashboardData();
    }

    onCompanyChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.company_id = val;
        this.fetchDashboardData();
    }

    selectDepartment(deptId) {
        if (deptId === "all") {
            this.state.department_ids = [];
        } else {
            this.state.department_ids = [deptId];
        }
        this.fetchDashboardData();
    }

    isDeptSelected(deptId) {
        if (deptId === "all") {
            return !this.state.department_ids || this.state.department_ids.length === 0;
        }
        return this.state.department_ids && this.state.department_ids.length === 1 && this.state.department_ids[0] === deptId;
    }

    sortBy(key) {
        if (this.state.sortKey === key) {
            this.state.sortOrder = this.state.sortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.sortKey = key;
            this.state.sortOrder = key === "department_name" ? "asc" : "desc";
        }
    }

    get sortedDepartments() {
        let depts = [...(this.data.departments || [])];
        const query = (this.state.searchQuery || "").trim().toLowerCase();

        if (query) {
            depts = depts.filter(d => (d.department_name || "").toLowerCase().includes(query));
        }

        const key = this.state.sortKey;
        const isAsc = this.state.sortOrder === "asc";

        if (!key) return depts;

        depts.sort((a, b) => {
            let valA = a[key];
            let valB = b[key];

            if (typeof valA === "string") {
                valA = (valA || "").toLowerCase();
                valB = (valB || "").toLowerCase();
                return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }

            valA = Number(valA) || 0;
            valB = Number(valB) || 0;
            return isAsc ? valA - valB : valB - valA;
        });

        return depts;
    }

    formatCurrency(amount) {
        if (amount === undefined || amount === null) return "0.000";
        return Number(amount).toLocaleString("en-US", {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3,
        });
    }

    formatDecimal(amount, decimals = 2) {
        if (amount === undefined || amount === null) return "0.00";
        return Number(amount).toLocaleString("en-US", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    }

    async onKpiClick(metricType) {
        try {
            const action = await this.orm.call(
                "hr.payroll.dashboard",
                "open_kpi_drilldown",
                [],
                {
                    metric_type: metricType,
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    payrun_id: this.state.payrun_id,
                    company_id: this.state.company_id,
                    department_ids: this.state.department_ids,
                }
            );

            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to open HR KPI drilldown action", error);
        }
    }

    async exportExcel() {
        try {
            const wizardVals = {
                date_from: this.state.date_from,
                date_to: this.state.date_to,
                report_type: "all",
            };
            if (this.state.payrun_id) {
                wizardVals.payrun_id = this.state.payrun_id;
            }
            if (this.state.company_id) {
                wizardVals.company_id = this.state.company_id;
            }
            if (this.state.department_ids && this.state.department_ids.length > 0) {
                wizardVals.department_ids = [[6, 0, this.state.department_ids]];
            }

            const wizard = await this.orm.create("hr.payroll.report.wizard", [wizardVals]);

            const action = await this.orm.call(
                "hr.payroll.report.wizard",
                "action_export_xlsx",
                [wizard[0]]
            );

            this.actionService.doAction(action);
        } catch (error) {
            console.error("Failed to export unified HR & Payroll Excel report", error);
        }
    }
}

registry.category("actions").add("hr_payroll_dashboard_main", HrPayrollDashboard);
