/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ExecutiveCompanyCostDashboard extends Component {
    static template = "executive_company_cost_dashboard.ExecutiveCompanyCostDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        this.trendCanvasRef = useRef("trendCanvas");
        this.donutCanvasRef = useRef("donutCanvas");

        this.trendChartInstance = null;
        this.donutChartInstance = null;

        this.state = useState({
            period_mode: "this_month",
            company_id: 0,
            branch_id: 0,
            activeTab: "overview",
            searchBranch: "",
            sortKey: "revenue",
            sortOrder: "desc",
            loading: true,
        });

        this.data = useState({
            period: {},
            currency: { name: "JOD", symbol: "د.أ" },
            kpis: {},
            buckets: [],
            sister_companies: [],
            departments: [],
            branches: [],
            monthly_trend: [],
            all_companies: [],
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });

        onMounted(() => {
            this.renderCharts();
        });
    }

    getFilters() {
        return {
            period_mode: this.state.period_mode,
            company_id: this.state.company_id,
            branch_id: this.state.branch_id,
        };
    }

    async loadDashboardData() {
        this.state.loading = true;
        try {
            const res = await this.orm.call(
                "ceo.cost.dashboard.report",
                "get_executive_dashboard_data",
                [this.getFilters()]
            );
            Object.assign(this.data, res);
            this.state.loading = false;
            // Allow DOM to update then draw charts
            setTimeout(() => this.renderCharts(), 50);
        } catch (error) {
            console.error("Failed to load CEO dashboard data:", error);
            this.state.loading = false;
            if (this.notification) {
                this.notification.add(
                    "Error loading financial data: " + (error.data?.message || error.message || error),
                    { type: "danger" }
                );
            }
        }
    }

    async setPeriod(mode) {
        this.state.period_mode = mode;
        await this.loadDashboardData();
    }

    async onCompanyChange(ev) {
        this.state.company_id = parseInt(ev.target.value) || 0;
        this.state.branch_id = 0;
        await this.loadDashboardData();
    }

    async onBranchChange(ev) {
        this.state.branch_id = parseInt(ev.target.value) || 0;
        await this.loadDashboardData();
    }

    setActiveTab(tab) {
        this.state.activeTab = tab;
        setTimeout(() => this.renderCharts(), 50);
    }

    formatCurrency(amount) {
        if (amount === undefined || amount === null) return "0.000";
        const sym = this.data.currency?.symbol || "د.أ";
        const formatted = Number(amount).toLocaleString(undefined, {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3,
        });
        return `${formatted} ${sym}`;
    }

    formatNumber(amount) {
        if (amount === undefined || amount === null) return "0.000";
        return Number(amount).toLocaleString(undefined, {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3,
        });
    }

    get filteredBranches() {
        let list = this.data.branches || [];
        const q = (this.state.searchBranch || "").toLowerCase().trim();
        if (q) {
            list = list.filter((b) => b.branch_name.toLowerCase().includes(q));
        }
        const key = this.state.sortKey;
        const asc = this.state.sortOrder === "asc" ? 1 : -1;
        return [...list].sort((a, b) => ((a[key] || 0) > (b[key] || 0) ? asc : -asc));
    }

    sortBy(key) {
        if (this.state.sortKey === key) {
            this.state.sortOrder = this.state.sortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.sortKey = key;
            this.state.sortOrder = "desc";
        }
    }

    async actionRunSmartScan() {
        await this.actionService.doAction("executive_company_cost_dashboard.action_ceo_smart_scanner_wizard", {
            onClose: async () => {
                await this.loadDashboardData();
            },
        });
    }

    renderCharts() {
        if (typeof Chart === "undefined") {
            return;
        }

        // 1. Render Monthly Trend Line Chart
        if (this.trendCanvasRef.el && this.data.monthly_trend?.length) {
            if (this.trendChartInstance) {
                this.trendChartInstance.destroy();
            }
            const ctx = this.trendCanvasRef.el.getContext("2d");
            const labels = this.data.monthly_trend.map((m) => m.month);
            const revenues = this.data.monthly_trend.map((m) => m.revenue);
            const opexs = this.data.monthly_trend.map((m) => m.opex);
            const profits = this.data.monthly_trend.map((m) => m.net_profit);

            this.trendChartInstance = new Chart(ctx, {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: "Total Revenue (الإيرادات)",
                            data: revenues,
                            borderColor: "#10b981",
                            backgroundColor: "rgba(16, 185, 129, 0.08)",
                            fill: true,
                            tension: 0.3,
                        },
                        {
                            label: "Total OpEx (المصاريف)",
                            data: opexs,
                            borderColor: "#ef4444",
                            backgroundColor: "rgba(239, 68, 68, 0.05)",
                            fill: true,
                            tension: 0.3,
                        },
                        {
                            label: "Net Profit (صافي الربح)",
                            data: profits,
                            borderColor: "#3b82f6",
                            borderDash: [5, 5],
                            tension: 0.3,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "top" },
                    },
                },
            });
        }

        // 2. Render Donut Chart for Cost Buckets
        if (this.donutCanvasRef.el && this.data.buckets?.length) {
            if (this.donutChartInstance) {
                this.donutChartInstance.destroy();
            }
            const ctx = this.donutCanvasRef.el.getContext("2d");
            const expenseBuckets = this.data.buckets.filter((b) => b.type === "expense" && b.amount > 0);
            const labels = expenseBuckets.map((b) => b.name);
            const amounts = expenseBuckets.map((b) => b.amount);
            const colors = expenseBuckets.map((b) => b.color || "#64748b");

            this.donutChartInstance = new Chart(ctx, {
                type: "doughnut",
                data: {
                    labels: labels,
                    datasets: [
                        {
                            data: amounts,
                            backgroundColor: colors,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "right" },
                    },
                },
            });
        }
    }
}

registry.category("actions").add("executive_company_cost_dashboard_main", ExecutiveCompanyCostDashboard);
