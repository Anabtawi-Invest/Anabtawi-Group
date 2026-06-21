/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { SalesRouteMap } from "../map/map";
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

export class SalesVisitDashboard extends Component {
    static template = "sales_visit_tracking.SalesVisitDashboard";
    static components = { SalesRouteMap };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            activeTab: 'assignments', // 'assignments', 'map', 'performance', 'coverage'
            data: {
                assignments: {
                    assigned: 0,
                    pending: 0,
                    completed: 0,
                    missed: 0,
                    revisit_schedule: []
                },
                performance: {
                    assigned_visits: 0,
                    completed_visits: 0,
                    new_leads_visited: 0,
                    approved_leads: 0,
                    rejected_leads: 0,
                    revisit_leads: 0,
                    customer_visits: 0,
                    orders_generated: 0,
                    revenue_generated: 0.0,
                    conversion_rate: 0.0,
                    gps_compliance: 100.0,
                    active_reps: 0
                },
                coverage: {
                    not_visited_30: [],
                    not_visited_60: [],
                    not_visited_90: []
                }
            }
        });

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            this.interval = setInterval(() => {
                this.loadData();
            }, 30000); // refresh every 30 seconds
        });

        onWillUnmount(() => {
            if (this.interval) {
                clearInterval(this.interval);
            }
        });
    }

    async loadData() {
        try {
            const res = await this.orm.call("sales.visit", "get_dashboard_data", []);
            this.state.data = res;
        } catch (error) {
            console.error("Failed to load dashboard data", error);
        }
    }

    onRefresh() {
        this.loadData();
    }

    switchTab(tab) {
        this.state.activeTab = tab;
    }

    onSchedule() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Schedule New Visit',
            res_model: 'sales.visit',
            views: [[false, 'form']],
            target: 'new',
            context: {}
        });
    }

    onAssign() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Manage Visit Assignments',
            res_model: 'sales.visit',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
            context: {'search_default_assigned': 1}
        });
    }
}

registry.category("actions").add("sales_visit_dashboard", SalesVisitDashboard);
