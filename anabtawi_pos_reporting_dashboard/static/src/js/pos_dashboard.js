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
        const now = new Date();
        const today6am = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const tomorrow5am = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);

        const initFrom = params.date_from || this._formatLocalDatetimeWithTime(today6am, "06", "00");
        const initTo = params.date_to || this._formatLocalDatetimeWithTime(tomorrow5am, "05", "00");
        const initConfigs = params.config_ids || [];

        this.state = useState({
            period: "today",
            date_from: initFrom,
            date_to: initTo,
            config_ids: initConfigs,
            loading: true,
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

    _formatLocalDatetimeWithTime(dateObj, hourStr = "06", minStr = "00") {
        if (!dateObj) return "";
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, "0");
        const day = String(dateObj.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}T${hourStr}:${minStr}`;
    }

    _formatDatetimeForRPC(valStr, isEnd = false) {
        if (!valStr) return "";
        let s = valStr.replace("T", " ");
        if (s.length === 10) {
            return isEnd ? `${s} 05:00:00` : `${s} 06:00:00`;
        }
        if (s.length === 16) {
            return `${s}:00`;
        }
        return s;
    }

    async fetchDashboardData() {
        this.state.loading = true;
        try {
            const strFrom = this._formatDatetimeForRPC(this.state.date_from, false);
            const strTo = this._formatDatetimeForRPC(this.state.date_to, true);

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
        let fromDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        let toDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);

        if (period === "today") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            toDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
        } else if (period === "yesterday") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
            toDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        } else if (period === "this_week") {
            const day = now.getDay();
            const diff = now.getDate() - day + (day === 0 ? -6 : 1);
            fromDate = new Date(now.getFullYear(), now.getMonth(), diff);
            toDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
        } else if (period === "this_month") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
            toDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
        }

        this.state.date_from = this._formatLocalDatetimeWithTime(fromDate, "06", "00");
        this.state.date_to = this._formatLocalDatetimeWithTime(toDate, "05", "00");
        this.fetchDashboardData();
    }

    formatCurrency(amount) {
        if (amount === undefined || amount === null) return "0.000";
        return Number(amount).toLocaleString("en-US", {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3,
        });
    }

    getPercent(value, total) {
        if (!total || total === 0) return "0.0";
        return ((value / total) * 100).toFixed(1);
    }

    async onKpiClick(metricType) {
        try {
            const strFrom = this._formatDatetimeForRPC(this.state.date_from, false);
            const strTo = this._formatDatetimeForRPC(this.state.date_to, true);

            const action = await this.orm.call(
                "pos.reporting.dashboard",
                "open_kpi_drilldown",
                [],
                {
                    metric_type: metricType,
                    date_from: strFrom,
                    date_to: strTo,
                    config_ids: this.state.config_ids,
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
            const strFrom = this._formatDatetimeForRPC(this.state.date_from, false);
            const strTo = this._formatDatetimeForRPC(this.state.date_to, true);

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
