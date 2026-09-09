/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class OnlineCampaignDashboard extends Component {
    static template = "online_campaigns_discount.OnlineCampaignDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        const now = new Date();
        const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
        const endOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);

        this.state = useState({
            period: "this_month",
            date_from: this._formatLocalDatetime(startOfMonth),
            date_to: this._formatLocalDatetime(endOfToday),
            aggregator_id: "",
            campaign_id: "",
            config_ids: [],
            loading: true,
        });

        this.data = useState({
            date_from: "",
            date_to: "",
            all_aggregators: [],
            all_campaigns: [],
            all_branches: [],
            kpis: {},
            aggregators: [],
            campaigns: [],
        });

        onWillStart(async () => {
            await this.fetchDashboardData();
        });
    }

    _formatLocalDatetime(dateObj) {
        if (!dateObj) return "";
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, "0");
        const day = String(dateObj.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}T00:00`;
    }

    _formatDatetimeForRPC(valStr) {
        if (!valStr) return "";
        let s = valStr.replace("T", " ");
        if (s.length === 10) {
            return `${s} 00:00:00`;
        }
        if (s.length === 16) {
            return `${s}:00`;
        }
        return s;
    }

    async fetchDashboardData() {
        this.state.loading = true;
        try {
            const strFrom = this._formatDatetimeForRPC(this.state.date_from);
            const strTo = this._formatDatetimeForRPC(this.state.date_to);

            const res = await this.orm.call(
                "online.campaign.dashboard",
                "get_dashboard_data",
                [],
                {
                    date_from: strFrom,
                    date_to: strTo,
                    aggregator_id: this.state.aggregator_id || false,
                    campaign_id: this.state.campaign_id || false,
                    config_ids: this.state.config_ids && this.state.config_ids.length ? this.state.config_ids : false,
                }
            );

            this.data.date_from = res.date_from || strFrom;
            this.data.date_to = res.date_to || strTo;
            this.data.all_aggregators = res.all_aggregators || [];
            this.data.all_campaigns = res.all_campaigns || [];
            this.data.all_branches = res.all_branches || [];
            this.data.kpis = res.kpis || {};
            this.data.aggregators = res.aggregators || [];
            this.data.campaigns = res.campaigns || [];
        } catch (error) {
            console.error("Failed to load Online Campaign dashboard data", error);
        } finally {
            this.state.loading = false;
        }
    }

    setPeriod(period) {
        this.state.period = period;
        const now = new Date();
        let fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
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

        this.state.date_from = this._formatLocalDatetime(fromDate);
        this.state.date_to = this._formatLocalDatetime(toDate);
        this.fetchDashboardData();
    }

    onAggregatorChange(ev) {
        this.state.aggregator_id = ev.target.value;
        this.fetchDashboardData();
    }

    onCampaignChange(ev) {
        this.state.campaign_id = ev.target.value;
        this.fetchDashboardData();
    }

    onBranchChange(ev) {
        const val = ev.target.value;
        this.state.config_ids = val ? [parseInt(val)] : [];
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

    async onKpiClick(metricType) {
        try {
            const strFrom = this._formatDatetimeForRPC(this.state.date_from);
            const strTo = this._formatDatetimeForRPC(this.state.date_to);

            const action = await this.orm.call(
                "online.campaign.dashboard",
                "open_kpi_drilldown",
                [],
                {
                    metric_type: metricType,
                    date_from: strFrom,
                    date_to: strTo,
                    aggregator_id: this.state.aggregator_id || false,
                    campaign_id: this.state.campaign_id || false,
                    config_ids: this.state.config_ids && this.state.config_ids.length ? this.state.config_ids : false,
                }
            );

            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to open KPI drilldown action", error);
        }
    }
}

registry.category("actions").add("online_campaign_dashboard_main", OnlineCampaignDashboard);
