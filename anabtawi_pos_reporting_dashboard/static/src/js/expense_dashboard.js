/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PosExpenseReportingDashboard extends Component {
    static template = "anabtawi_pos_reporting_dashboard.PosExpenseReportingDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        const params = this.props.action?.params || {};
        const today = this._formatLocalDate(new Date());

        this.state = useState({
            period: "today",
            date_from: (params.date_from || today).slice(0, 10),
            date_to: (params.date_to || today).slice(0, 10),
            config_ids: params.config_ids || [],
            loading: true,
            sortKey: "amount",
            sortOrder: "desc",
            branchSortKey: "expense_amount",
            branchSortOrder: "desc",
        });

        this.data = useState({
            date_from: "",
            date_to: "",
            all_branches: [],
            kpis: {},
            branches: [],
            accounts: [],
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
                "pos.reporting.dashboard",
                "get_expense_dashboard_data",
                [],
                {
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    config_ids: this.state.config_ids,
                }
            );
            this.data.date_from = res.date_from || this.state.date_from;
            this.data.date_to = res.date_to || this.state.date_to;
            this.data.kpis = res.kpis || {};
            this.data.branches = res.branches || [];
            this.data.accounts = res.accounts || [];
            this.data.all_branches = res.all_branches || [];
        } catch (error) {
            console.error("Failed to load Expenses dashboard data", error);
        } finally {
            this.state.loading = false;
        }
    }

    get sortedAccounts() {
        const rows = [...(this.data.accounts || [])];
        const key = this.state.sortKey;
        const isAsc = this.state.sortOrder === "asc";
        if (!key) return rows;
        rows.sort((a, b) => {
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
        return rows;
    }

    get sortedBranches() {
        const rows = [...(this.data.branches || [])];
        const key = this.state.branchSortKey;
        const isAsc = this.state.branchSortOrder === "asc";
        if (!key) return rows;
        rows.sort((a, b) => {
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
        return rows;
    }

    sortAccountsBy(key) {
        if (this.state.sortKey === key) {
            this.state.sortOrder = this.state.sortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.sortKey = key;
            this.state.sortOrder = key === "account_name" || key === "account_code" ? "asc" : "desc";
        }
    }

    sortBranchesBy(key) {
        if (this.state.branchSortKey === key) {
            this.state.branchSortOrder = this.state.branchSortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.branchSortKey = key;
            this.state.branchSortOrder = key === "branch_name" ? "asc" : "desc";
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

    getPercent(value, total) {
        if (!total || total === 0) return "0.0";
        return ((value / total) * 100).toFixed(1);
    }

    async onPosExpenseClick(configId = null) {
        try {
            const targetConfigs = configId ? [configId] : (this.state.config_ids || []);
            const action = await this.orm.call(
                "pos.reporting.dashboard",
                "open_kpi_drilldown",
                [],
                {
                    metric_type: "expense_amount",
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    config_ids: targetConfigs,
                }
            );
            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to open POS expense drilldown", error);
        }
    }

    async onAccountExpenseClick(accountId = null) {
        try {
            const action = await this.orm.call(
                "pos.reporting.dashboard",
                "open_account_expense_drilldown",
                [],
                {
                    account_id: accountId || null,
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                }
            );
            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to open account expense drilldown", error);
        }
    }

    async openAccountConfig() {
        this.actionService.doAction("anabtawi_pos_reporting_dashboard.action_pos_expense_dashboard_account");
    }
}

registry.category("actions").add("pos_expense_reporting_dashboard_main", PosExpenseReportingDashboard);
