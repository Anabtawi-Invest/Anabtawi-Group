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
            loading: true,
            sortKey: "amount",
            sortOrder: "desc",
        });

        this.data = useState({
            date_from: "",
            date_to: "",
            kpis: {},
            accounts: [],
        });
        this._requestId = 0;

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
        const requestId = ++this._requestId;
        const strFrom = this.state.date_from;
        const strTo = this.state.date_to;
        this.state.loading = true;
        try {
            const res = await this.orm.call(
                "pos.reporting.dashboard",
                "get_expense_dashboard_data",
                [],
                {
                    date_from: strFrom,
                    date_to: strTo,
                }
            );
            if (requestId !== this._requestId) {
                return;
            }
            this.data.date_from = res.date_from || strFrom;
            this.data.date_to = res.date_to || strTo;
            this.state.date_from = this.data.date_from;
            this.state.date_to = this.data.date_to;
            this.data.kpis = res.kpis || {};
            this.data.accounts = res.accounts || [];
        } catch (error) {
            console.error("Failed to load Expenses dashboard data", error);
        } finally {
            if (requestId === this._requestId) {
                this.state.loading = false;
            }
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

    sortAccountsBy(key) {
        if (this.state.sortKey === key) {
            this.state.sortOrder = this.state.sortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.sortKey = key;
            this.state.sortOrder = key === "account_name" || key === "account_code" ? "asc" : "desc";
        }
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

    onDateChange(field, ev) {
        const value = (ev.target.value || "").slice(0, 10);
        if (!value || value === this.state[field]) {
            return;
        }
        this.state.period = "custom";
        this.state[field] = value;
        this.fetchDashboardData();
    }

    applyFilters(ev) {
        const bar = ev.currentTarget.closest(".o_dashboard_filters");
        const inputs = bar ? bar.querySelectorAll("input[type='date']") : [];
        const fromValue = (inputs[0]?.value || this.state.date_from || "").slice(0, 10);
        const toValue = (inputs[1]?.value || this.state.date_to || "").slice(0, 10);
        if (fromValue && fromValue !== this.state.date_from) {
            this.state.date_from = fromValue;
            this.state.period = "custom";
        }
        if (toValue && toValue !== this.state.date_to) {
            this.state.date_to = toValue;
            this.state.period = "custom";
        }
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

    async onPosExpenseClick() {
        try {
            const action = await this.orm.call(
                "pos.reporting.dashboard",
                "open_expense_dashboard_pos_drilldown",
                [],
                {
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
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
