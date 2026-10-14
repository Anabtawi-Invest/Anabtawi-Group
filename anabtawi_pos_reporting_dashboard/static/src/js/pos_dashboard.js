/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PosReportingDashboard extends Component {
    static template = "anabtawi_pos_reporting_dashboard.PosReportingDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        const params = this.props.action?.params || {};
        const today = this._formatLocalDate(new Date());

        const initFrom = (params.date_from || today).slice(0, 10);
        const initTo = (params.date_to || today).slice(0, 10);
        const initConfigs = params.config_ids || [];

        this.state = useState({
            period: "today",
            date_from: initFrom,
            date_to: initTo,
            config_ids: initConfigs,
            loading: true,
            sortKey: "sales",
            sortOrder: "desc",
        });

        this.data = useState({
            date_from: "",
            date_to: "",
            active_branches_count: 0,
            all_branches: [],
            kpis: {},
            branches: [],
            global_totals: {},
            channels: [],
            trends: [],
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
            const strFrom = this.state.date_from;
            const strTo = this.state.date_to;

            const res = await this.orm.call(
                "pos.reporting.dashboard",
                "get_dashboard_data",
                [],
                {
                    date_from: strFrom,
                    date_to: strTo,
                    config_ids: this.state.config_ids,
                }
            );

            this.data.date_from = res.date_from || strFrom;
            this.data.date_to = res.date_to || strTo;
            this.data.kpis = res.kpis || {};
            this.data.branches = res.branches || [];
            this.data.all_branches = res.all_branches || [];
            this.data.global_totals = res.global_totals || {};
            this.data.channels = res.channels || [];
            this.data.trends = res.trends || [];
        } catch (error) {
            console.error("Failed to load POS dashboard data", error);
        } finally {
            this.state.loading = false;
        }
    }

    get sortedBranches() {
        const branches = [...(this.data.branches || [])];
        const key = this.state.sortKey;
        const isAsc = this.state.sortOrder === "asc";

        if (!key) return branches;

        branches.sort((a, b) => {
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

        return branches;
    }

    sortBy(key) {
        if (this.state.sortKey === key) {
            this.state.sortOrder = this.state.sortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.sortKey = key;
            this.state.sortOrder = key === "branch_name" ? "asc" : "desc";
        }
    }

    selectBranch(branchId) {
        if (branchId === "all") {
            this.state.config_ids = [];
        } else {
            this.state.config_ids = [branchId];
        }
        this.fetchDashboardData();
    }

    isBranchSelected(branchId) {
        if (branchId === "all") {
            return !this.state.config_ids || this.state.config_ids.length === 0;
        }
        return this.state.config_ids && this.state.config_ids.length === 1 && this.state.config_ids[0] === branchId;
    }

    setPeriod(period) {
        this.state.period = period;
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        let fromDate = today;
        let toDate = today;

        if (period === "yesterday") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
            toDate = fromDate;
        } else if (period === "this_week") {
            const day = now.getDay();
            const diff = now.getDate() - day + (day === 0 ? -6 : 1);
            fromDate = new Date(now.getFullYear(), now.getMonth(), diff);
        } else if (period === "this_month") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
        }

        this.state.date_from = this._formatLocalDate(fromDate);
        this.state.date_to = this._formatLocalDate(toDate);
        this.fetchDashboardData();
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

    getPercent(value, total) {
        if (!total || total === 0) return "0.0";
        return ((value / total) * 100).toFixed(1);
    }

    async onKpiClick(metricType, configId = null) {
        try {
            const strFrom = this.state.date_from;
            const strTo = this.state.date_to;
            const targetConfigs = configId ? [configId] : (this.state.config_ids || []);

            const action = await this.orm.call(
                "pos.reporting.dashboard",
                "open_kpi_drilldown",
                [],
                {
                    metric_type: metricType,
                    date_from: strFrom,
                    date_to: strTo,
                    config_ids: targetConfigs,
                }
            );

            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to open KPI drilldown action", error);
        }
    }

    async exportExcel() {
        try {
            const strFrom = this.state.date_from;
            const strTo = this.state.date_to;

            const wizardVals = {
                date_from: strFrom,
                date_to: strTo,
            };
            if (this.state.config_ids && this.state.config_ids.length > 0) {
                wizardVals.config_ids = [[6, 0, this.state.config_ids]];
            }

            const wizard = await this.orm.create("pos.unified.report.wizard", [wizardVals]);

            const action = await this.orm.call(
                "pos.unified.report.wizard",
                "action_export_xlsx",
                [wizard[0]]
            );

            this.actionService.doAction(action);
        } catch (error) {
            console.error("Failed to export Excel report", error);
        }
    }
}

registry.category("actions").add("pos_reporting_dashboard_main", PosReportingDashboard);
