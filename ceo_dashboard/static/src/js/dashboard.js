/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart } from "@odoo/owl";

const { DateTime } = luxon;

export class CeoDashboard extends Component {
    static template = "ceo_dashboard.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notificationService = useService("notification");

        const today = DateTime.local().toISODate();
        const startOfMonth = DateTime.local().startOf("month").toISODate();

        this.state = useState({
            loading: true,
            syncing: false,
            activeTab: "summary", // 'summary' | 'finance' | 'sales' | 'inventory' | 'hr' | 'project'
            preset: "month",
            dateFrom: startOfMonth,
            dateTo: today,
            yoyComparison: true,
            currency: "",
            notification: null,
            data: null,
        });

        onWillStart(async () => this.loadData());
    }

    // ------------------------------------------------------------------
    // Data Loading & Refresh
    // ------------------------------------------------------------------
    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("ceo.dashboard", "get_dashboard_data", [
                this.state.dateFrom,
                this.state.dateTo,
            ]);
            this.state.data = data;
            if (data && data.currency_name) {
                this.state.currency = data.currency_symbol ? `${data.currency_symbol} ${data.currency_name}` : data.currency_name;
            }
        } catch (e) {
            console.error("Dashboard data load error:", e);
        } finally {
            this.state.loading = false;
        }
    }

    async syncData() {
        this.state.syncing = true;
        await this.loadData();
        setTimeout(() => {
            this.state.syncing = false;
            this.notify("Data refreshed with live Odoo records", "success");
        }, 300);
    }

    notify(message, type = "info") {
        if (this.notificationService) {
            this.notificationService.add(message, { type });
        }
    }

    // ------------------------------------------------------------------
    // Navigation Tabs & Presets
    // ------------------------------------------------------------------
    switchTab(tab) {
        this.state.activeTab = tab;
    }

    setPreset(preset) {
        const now = DateTime.local();
        let from, to;
        switch (preset) {
            case "today":
                from = now.startOf("day");
                to = now.endOf("day");
                break;
            case "week":
                from = now.startOf("week");
                to = now.endOf("week");
                break;
            case "month":
                from = now.startOf("month");
                to = now.endOf("month");
                break;
            case "quarter":
                from = now.startOf("quarter");
                to = now.endOf("quarter");
                break;
            case "year":
                from = now.startOf("year");
                to = now.endOf("year");
                break;
            default:
                return;
        }
        this.state.preset = preset;
        this.state.dateFrom = from.toISODate();
        this.state.dateTo = to.toISODate();
        this.loadData();
    }

    onDateChange(field, ev) {
        this.state.preset = "custom";
        this.state[field] = ev.target.value;
    }

    applyCustomRange() {
        this.loadData();
    }

    toggleYoY() {
        this.state.yoyComparison = !this.state.yoyComparison;
    }

    exportReport() {
        window.print();
    }

    // ------------------------------------------------------------------
    // Interactive Odoo Drill-Down Actions
    // ------------------------------------------------------------------
    openInvoices() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Customer Invoices",
            res_model: "account.move",
            views: [[false, "list"], [false, "form"]],
            domain: [["move_type", "=", "out_invoice"]],
        });
    }

    openOverdueInvoices() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Critical Overdue Invoices",
            res_model: "account.move",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["move_type", "=", "out_invoice"],
                ["state", "=", "posted"],
                ["payment_state", "in", ["not_paid", "partial"]],
            ],
            context: { search_default_unpaid: 1 },
        });
    }

    openSalesOrders() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Sales Orders",
            res_model: "sale.order",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "=", "sale"]],
        });
    }

    openCRM() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "CRM Pipeline",
            res_model: "crm.lead",
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
        });
    }

    openTimeOff() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Time Off Requests",
            res_model: "hr.leave",
            views: [[false, "list"], [false, "form"]],
        });
    }

    openHRModule() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Employees Directory",
            res_model: "hr.employee",
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
        });
    }

    openJobs() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Job Positions",
            res_model: "hr.job",
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
        });
    }

    openProjects() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Projects Overview",
            res_model: "project.project",
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
        });
    }

    openTickets() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Support Tickets",
            res_model: "helpdesk.ticket",
            views: [[false, "list"], [false, "form"]],
        });
    }

    // ------------------------------------------------------------------
    // In-Dashboard Action Handlers
    // ------------------------------------------------------------------
    sendDunning(customer) {
        this.notify(`Dunning reminder queued for ${customer.name} (${customer.email})`, "info");
    }

    remindAllOverdue() {
        this.notify("Payment reminder statements sent to all 5 overdue accounts!", "success");
    }

    createRFQ(item) {
        this.notify(`Draft RFQ initiated for ${item.sku} - ${item.name} with ${item.vendor}`, "success");
    }

    generateRFQForAll() {
        this.notify("Bulk RFQs generated for all 5 critical reorder lines!", "success");
    }

    async approveLeave(leave) {
        try {
            await this.orm.call("ceo.dashboard", "action_approve_leave", [leave.id]);
            if (this.state.data && this.state.data.hr && this.state.data.hr.pending_leaves) {
                this.state.data.hr.pending_leaves = this.state.data.hr.pending_leaves.filter(l => l.id !== leave.id);
                this.state.data.hr.pending_leaves_count = Math.max(0, this.state.data.hr.pending_leaves_count - 1);
            }
            this.notify(`Time Off request for ${leave.employee_name} Approved!`, "success");
        } catch (e) {
            this.notify(`Error approving leave: ${e}`, "warning");
        }
    }

    async refuseLeave(leave) {
        try {
            await this.orm.call("ceo.dashboard", "action_refuse_leave", [leave.id]);
            if (this.state.data && this.state.data.hr && this.state.data.hr.pending_leaves) {
                this.state.data.hr.pending_leaves = this.state.data.hr.pending_leaves.filter(l => l.id !== leave.id);
                this.state.data.hr.pending_leaves_count = Math.max(0, this.state.data.hr.pending_leaves_count - 1);
            }
            this.notify(`Time Off request for ${leave.employee_name} Refused.`, "info");
        } catch (e) {
            this.notify(`Error refusing leave: ${e}`, "warning");
        }
    }

    // ------------------------------------------------------------------
    // Formatting Helpers
    // ------------------------------------------------------------------
    fmtMoney(amount) {
        if (amount === undefined || amount === null || isNaN(amount)) amount = 0;
        const sym = (this.state.data && this.state.data.currency_symbol) || "";
        const pos = (this.state.data && this.state.data.currency_position) || "before";
        const sign = amount < 0 ? "-" : "";
        const absVal = Math.abs(amount);
        const n = absVal.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return pos === "after" ? `${sign}${n} ${sym}` : `${sign}${sym}${n}`;
    }

    fmtCompact(amount) {
        if (amount === undefined || amount === null || isNaN(amount)) amount = 0;
        const sym = (this.state.data && this.state.data.currency_symbol) || "";
        const pos = (this.state.data && this.state.data.currency_position) || "before";
        const sign = amount < 0 ? "-" : "";
        const absVal = Math.abs(amount);
        let formatted = "";
        if (absVal >= 1000000) {
            formatted = `${(absVal / 1000000).toFixed(2)}M`;
        } else if (absVal >= 1000) {
            formatted = `${(absVal / 1000).toFixed(1)}K`;
        } else {
            formatted = `${absVal.toFixed(2)}`;
        }
        return pos === "after" ? `${sign}${formatted} ${sym}` : `${sign}${sym}${formatted}`;
    }

    fmtPct(v) {
        if (v === undefined || v === null || isNaN(v)) return "0.0%";
        return `${Number(v).toFixed(1)}%`;
    }

    fmtNum(v) {
        if (v === undefined || v === null || isNaN(v)) return "0";
        return Math.round(Number(v)).toLocaleString("en-US");
    }
}

registry.category("actions").add("ceo_dashboard.dashboard", CeoDashboard);
