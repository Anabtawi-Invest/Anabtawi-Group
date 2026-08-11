/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PosReportingDashboard extends Component {
    static template = "anabtawi_pos_reporting_dashboard.PosReportingDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        const today = new Date().toISOString().split("T")[0];

        this.state = useState({
            period: "today",
            date_from: today,
            date_to: today,
            config_ids: [],
            loading: true,
        });

        this.data = useState({
            kpis: {},
            branches: [],
            all_branches: [],
            global_totals: {},
            channels: [],
            trends: [],
        });

        if (this.props.action && this.props.action.params) {
            const p = this.props.action.params;
            if (p.date_from) this.state.date_from = p.date_from;
            if (p.date_to) this.state.date_to = p.date_to;
            if (p.config_ids) this.state.config_ids = p.config_ids;
        }

        onWillStart(async () => {
            await this.fetchDashboardData();
        });
    }

    async fetchDashboardData() {
        this.state.loading = true;
        try {
            const res = await this.orm.call(
                "pos.reporting.dashboard",
                "get_dashboard_data",
                [],
                {
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    config_ids: this.state.config_ids,
                }
            );

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

        this.state.date_from = fromDate.toISOString().split("T")[0];
        this.state.date_to = toDate.toISOString().split("T")[0];
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
            const wizard = await this.orm.create("pos.unified.report.wizard", [
                {
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    config_ids: this.state.config_ids && this.state.config_ids.length ? [[6, 0, this.state.config_ids]] : [],
                },
            ]);
            if (wizard && wizard.length) {
                window.location.href = `/pos_unified_report/xlsx/${wizard[0]}`;
            }
        } catch (error) {
            console.error("Failed to export POS report Excel", error);
        }
    }
}

registry.category("actions").add("pos_reporting_dashboard_main", PosReportingDashboard);
