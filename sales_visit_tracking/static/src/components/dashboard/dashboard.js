/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

export class SalesVisitDashboard extends Component {
    static template = "sales_visit_tracking.SalesVisitDashboard";
    
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            kpis: {
                today_visits: 0,
                completed_visits: 0,
                missed_visits: 0,
                revisit_count: 0,
                approved_count: 0,
                rejected_count: 0,
                gps_compliance: 100,
                active_reps: 0
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
            this.state.kpis = await this.orm.call("sales.visit", "get_dashboard_data", []);
        } catch (error) {
            console.error("Failed to load dashboard KPIs", error);
        }
    }

    onRefresh() {
        this.loadData();
    }
}

registry.category("actions").add("sales_visit_dashboard", SalesVisitDashboard);
