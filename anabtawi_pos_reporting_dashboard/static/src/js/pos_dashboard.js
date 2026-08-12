/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PosReportingDashboard extends Component {
    static template = "anabtawi_pos_reporting_dashboard.PosReportingDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        const now = new Date();

        this.state = useState({
            period: "today",
            date_from: this._formatLocalDatetime(now, false),
            date_to: this._formatLocalDatetime(now, true),
            config_ids: [],
            loading: true,
        });

        this.data = useState({
            date_from: "",
            date_to: "",
            kpis: {},
            branches: [],
            all_branches: [],
            global_totals: {},
            channels: [],
            trends: [],
        });

        if (this.props.action && this.props.action.params) {
            const p = this.props.action.params;
            if (p.date_from) this.state.date_from = p.date_from.replace(" ", "T").slice(0, 16);
            if (p.date_to) this.state.date_to = p.date_to.replace(" ", "T").slice(0, 16);
            if (p.config_ids) this.state.config_ids = p.config_ids;
        }

        onWillStart(async () => {
            await this.fetchDashboardData();
        });
    }

    _formatLocalDatetime(dateObj, isEnd = false) {
        if (!dateObj) return "";
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, "0");
        const day = String(dateObj.getDate()).padStart(2, "0");
        const hours = isEnd ? "23" : "00";
        const mins = isEnd ? "59" : "00";
        return `${year}-${month}-${day}T${hours}:${mins}`;
    }

    _formatDatetimeForRPC(valStr, isEnd = false) {
        if (!valStr) return "";
        let s = valStr.replace("T", " ");
        if (s.length === 10) {
            return isEnd ? `${s} 23:59:59` : `${s} 00:00:00`;
        }
        if (s.length === 16) {
            return isEnd ? `${s}:59` : `${s}:00`;
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
        let fromDate = new Date();
        let toDate = new Date();

        if (period === "today") {
            // default
        } else if (period === "yesterday") {
            fromDate.setDate(now.getDate() - 1);
            toDate.setDate(now.getDate() - 1);
        } else if (period === "this_week") {
            const day = now.getDay();
            const diff = now.getDate() - day + (day === 0 ? -6 : 1);
            fromDate = new Date(now.setDate(diff));
            toDate = new Date();
        } else if (period === "this_month") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
            toDate = new Date();
        }

        this.state.date_from = this._formatLocalDatetime(fromDate, false);
        this.state.date_to = this._formatLocalDatetime(toDate, true);
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

    async exportExcel() {
        try {
            const strFrom = this._formatDatetimeForRPC(this.state.date_from, false);
            const strTo = this._formatDatetimeForRPC(this.state.date_to, true);

            const wizard = await this.orm.create("pos.unified.report.wizard", [
                {
                    date_from: strFrom,
                    date_to: strTo,
                    config_ids: [[6, 0, this.state.config_ids]],
                },
            ]);

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
