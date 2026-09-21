/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class HrPayrollDashboard extends Component {
    static template = "anabtawi_hr_payroll_dashboard.HrPayrollDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

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
            expandedParents: [],
            searchQuery: "",
            sortKey: "net_salary",
            sortOrder: "desc",
            loading: true,
            exportingExcel: false,
        });

        this.data = useState({
            date_from: "",
            date_to: "",
            selected_company_id: 0,
            selected_payrun_id: 0,
            payrun_batches: [],
            all_departments: [],
            parent_departments: [],
            all_companies: [],
            kpis: {},
            departments: [],
            channels: [],
            operational_highlights: {
                scheduled_hours: 0,
                approved_hours: 0,
                extra_ot_hours: 0,
                subtracted_late_hours: 0,
                top_ot_departments: [],
                top_late_departments: [],
                top_headcount_departments: [],
            },
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

            const op = res?.operational_highlights || {};
            this.data.date_from = res?.date_from || this.state.date_from;
            this.data.date_to = res?.date_to || this.state.date_to;
            this.data.selected_company_id = res?.selected_company_id || 0;
            this.data.selected_payrun_id = res?.selected_payrun_id || 0;
            this.data.payrun_batches = res?.payrun_batches || [];
            this.data.all_departments = res?.all_departments || [];
            this.data.parent_departments = res?.parent_departments || [];
            this.data.all_companies = res?.all_companies || [];
            this.data.kpis = res?.kpis || {};
            this.data.departments = res?.departments || [];
            this.data.channels = res?.channels || [];
            this.data.operational_highlights = {
                scheduled_hours: op.scheduled_hours || 0,
                approved_hours: op.approved_hours || 0,
                extra_ot_hours: op.extra_ot_hours || 0,
                subtracted_late_hours: op.subtracted_late_hours || 0,
                top_ot_departments: op.top_ot_departments || [],
                top_late_departments: op.top_late_departments || [],
                top_headcount_departments: op.top_headcount_departments || [],
            };
        } catch (error) {
            console.error("Failed to load HR & Payroll dashboard data", error);
            if (this.notification) {
                this.notification.add(
                    "Error loading dashboard: " + (error.data?.message || error.message || error),
                    { type: "danger" }
                );
            }
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
        this.state.payrun_id = 0;
        this.fetchDashboardData();
    }

    onPayrunChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.payrun_id = val;
        this.fetchDashboardData();
    }

    selectCompany(compId) {
        this.state.company_id = parseInt(compId) || 0;
        this.state.department_ids = [];
        this.state.expandedParents = [];
        this.fetchDashboardData();
    }

    isCompanySelected(compId) {
        return (this.state.company_id || 0) === (parseInt(compId) || 0);
    }

    // Toggle expand/fold of a parent department's child branches
    toggleParentExpand(parentId, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        const pId = parseInt(parentId);
        const idx = this.state.expandedParents.indexOf(pId);
        if (idx > -1) {
            this.state.expandedParents.splice(idx, 1);
        } else {
            this.state.expandedParents.push(pId);
        }
    }

    isParentExpanded(parentId) {
        return this.state.expandedParents.includes(parseInt(parentId));
    }

    // Multi-Select Department toggle
    toggleDepartment(deptId, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        const id = parseInt(deptId);
        const current = [...this.state.department_ids];
        const idx = current.indexOf(id);

        if (idx > -1) {
            current.splice(idx, 1);
        } else {
            current.push(id);
        }
        this.state.department_ids = current;
        this.fetchDashboardData();
    }

    // Select or toggle parent and all its children together
    toggleParentWithChildren(parentDept, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        const parentId = parseInt(parentDept.id);
        const childIds = (parentDept.children || []).map(c => parseInt(c.id));
        const allIds = [parentId, ...childIds];

        const current = [...this.state.department_ids];
        const allAlreadySelected = allIds.every(id => current.includes(id));

        if (allAlreadySelected) {
            // Deselect all
            this.state.department_ids = current.filter(id => !allIds.includes(id));
        } else {
            // Select all
            const newSet = new Set([...current, ...allIds]);
            this.state.department_ids = Array.from(newSet);
            // Also expand parent if not already expanded so user sees the branches
            if (!this.state.expandedParents.includes(parentId)) {
                this.state.expandedParents.push(parentId);
            }
        }
        this.fetchDashboardData();
    }

    selectAllDepartments() {
        this.state.department_ids = [];
        this.fetchDashboardData();
    }

    isDeptSelected(deptId) {
        if (deptId === "all") {
            return !this.state.department_ids || this.state.department_ids.length === 0;
        }
        return this.state.department_ids && this.state.department_ids.includes(parseInt(deptId));
    }

    isParentPartiallySelected(parentDept) {
        if (!this.state.department_ids || this.state.department_ids.length === 0) return false;
        const parentId = parseInt(parentDept.id);
        const childIds = (parentDept.children || []).map(c => parseInt(c.id));
        const allIds = [parentId, ...childIds];
        const hasSome = allIds.some(id => this.state.department_ids.includes(id));
        const hasAll = allIds.every(id => this.state.department_ids.includes(id));
        return hasSome && !hasAll;
    }

    isParentFullySelected(parentDept) {
        if (!this.state.department_ids || this.state.department_ids.length === 0) return false;
        const parentId = parseInt(parentDept.id);
        const childIds = (parentDept.children || []).map(c => parseInt(c.id));
        const allIds = [parentId, ...childIds];
        return allIds.every(id => this.state.department_ids.includes(id));
    }

    getSelectedCountForParent(parentDept) {
        if (!this.state.department_ids || this.state.department_ids.length === 0) return 0;
        const childIds = (parentDept.children || []).map(c => parseInt(c.id));
        const allIds = [parseInt(parentDept.id), ...childIds];
        return allIds.filter(id => this.state.department_ids.includes(id)).length;
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
                // Safeguard against missing action.views which causes TypeError in Odoo web client
                if (!action.views && action.view_mode) {
                    action.views = action.view_mode.split(",").map(v => [false, v.trim()]);
                }
                await this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to open HR KPI drilldown action", error);
            if (this.notification) {
                this.notification.add(
                    "Could not open drilldown: " + (error.data?.message || error.message || error),
                    { type: "danger" }
                );
            }
        }
    }

    async exportExcel() {
        if (this.state.exportingExcel) return;
        this.state.exportingExcel = true;

        if (this.notification) {
            this.notification.add(
                "Generating unified HR & Payroll Excel package...",
                { type: "info" }
            );
        }

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
                wizardVals.department_ids = [[6, 0, this.state.department_ids.map(Number)]];
            }

            const wizardRes = await this.orm.create("hr.payroll.report.wizard", [wizardVals]);
            const wizardId = Array.isArray(wizardRes) ? wizardRes[0] : wizardRes;

            const action = await this.orm.call(
                "hr.payroll.report.wizard",
                "action_export_xlsx",
                [wizardId]
            );

            if (action && action.type === "ir.actions.act_url" && action.url) {
                window.location.href = action.url;
                if (this.notification) {
                    this.notification.add(
                        "Excel file exported successfully.",
                        { type: "success" }
                    );
                }
            } else if (action) {
                if (!action.views && action.view_mode) {
                    action.views = action.view_mode.split(",").map(v => [false, v.trim()]);
                }
                await this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to export unified HR & Payroll Excel report", error);
            if (this.notification) {
                this.notification.add(
                    "Export failed: " + (error.data?.message || error.message || error),
                    { type: "danger" }
                );
            }
        } finally {
            this.state.exportingExcel = false;
        }
    }
}

registry.category("actions").add("hr_payroll_dashboard_main", HrPayrollDashboard);
