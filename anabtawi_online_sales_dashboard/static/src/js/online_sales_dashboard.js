/** @odoo-module **/

import { Component, onWillStart, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class OnlineSalesDashboard extends Component {
    static template = "anabtawi_online_sales_dashboard.OnlineSalesDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.chartInstances = {};

        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

        this.state = useState({
            isLoading: true,
            dateFrom: firstDay.toISOString().split('T')[0],
            dateTo: today.toISOString().split('T')[0],
            data: {
                summary: {},
                channel_breakdown: [],
                branch_breakdown: [],
                hourly_trend: [],
                top_products: [],
                top_categories: [],
            },
        });

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.loadDashboardData();
        });

        onMounted(() => {
            this.renderCharts();
        });
    }

    async loadDashboardData() {
        this.state.isLoading = true;
        try {
            const result = await this.orm.call(
                "online.sales.dashboard",
                "get_online_dashboard_data",
                [],
                {
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                }
            );
            this.state.data = result;
        } catch (error) {
            console.error("Failed to load online sales dashboard data", error);
        } finally {
            this.state.isLoading = false;
            setTimeout(() => this.renderCharts(), 100);
        }
    }

    async onFilterChange() {
        await this.loadDashboardData();
    }

    renderCharts() {
        if (this.state.isLoading || !this.state.data) return;

        // 1. Channel Breakdown Pie Chart
        const ctxPie = document.getElementById("canvas_channel_pie");
        if (ctxPie) {
            if (this.chartInstances.pie) {
                this.chartInstances.pie.destroy();
            }
            const channels = this.state.data.channel_breakdown || [];
            this.chartInstances.pie = new window.Chart(ctxPie, {
                type: "doughnut",
                data: {
                    labels: channels.map(c => c.name),
                    datasets: [{
                        data: channels.map(c => c.gross_amount),
                        backgroundColor: channels.map(c => c.color),
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    legend: {
                        position: "right",
                        labels: { fontColor: "#0f172a", fontSize: 12, fontStyle: "bold" }
                    },
                }
            });
        }

        // 2. Hourly Delivery Trend Line Chart
        const ctxHourly = document.getElementById("canvas_hourly_trend");
        if (ctxHourly) {
            if (this.chartInstances.hourly) {
                this.chartInstances.hourly.destroy();
            }
            const hourly = this.state.data.hourly_trend || [];
            this.chartInstances.hourly = new window.Chart(ctxHourly, {
                type: "line",
                data: {
                    labels: hourly.map(h => h.hour),
                    datasets: [{
                        label: "Gross Sales (JOD)",
                        data: hourly.map(h => h.gross_amount),
                        borderColor: "#2563eb",
                        backgroundColor: "rgba(37, 99, 235, 0.15)",
                        borderWidth: 3,
                        pointBackgroundColor: "#2563eb",
                        pointRadius: 4,
                        fill: true,
                        tension: 0.3,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    legend: {
                        labels: { fontColor: "#0f172a", fontSize: 12, fontStyle: "bold" }
                    },
                    scales: {
                        xAxes: [{
                            ticks: { fontColor: "#0f172a", fontStyle: "bold" },
                            gridLines: { color: "#e2e8f0" }
                        }],
                        yAxes: [{
                            ticks: { beginAtZero: true, fontColor: "#0f172a", fontStyle: "bold" },
                            gridLines: { color: "#e2e8f0" }
                        }]
                    }
                }
            });
        }
    }

    async onDrilldownChannel(channelCode) {
        const action = await this.orm.call(
            "online.sales.dashboard",
            "get_online_sales_drilldown",
            [],
            {
                channel_code: channelCode,
                date_from: this.state.dateFrom,
                date_to: this.state.dateTo,
            }
        );
        this.action.doAction(action);
    }

    async onDrilldownBranch(branchName) {
        const action = await this.orm.call(
            "online.sales.dashboard",
            "get_online_sales_drilldown",
            [],
            {
                branch_name: branchName,
                date_from: this.state.dateFrom,
                date_to: this.state.dateTo,
            }
        );
        this.action.doAction(action);
    }

    onExportExcel() {
        this.action.doAction({
            name: "Export Online Sales Excel",
            type: "ir.actions.act_window",
            res_model: "online.sales.report.wizard",
            view_mode: "form",
            target: "new",
            context: {
                default_date_from: this.state.dateFrom,
                default_date_to: this.state.dateTo,
            },
        });
    }
}

registry.category("actions").add("online_sales_dashboard_tag", OnlineSalesDashboard);
