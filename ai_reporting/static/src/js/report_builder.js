/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

export class AiReportingReportBuilder extends Component {
    static template = "ai_reporting.ReportBuilder";

    setup() {
        this.notification = useService("notification");
        this.state = useState({
            question: "",
            adjustment: "",
            requestId: null,
            savedReportId: null,
            status: "draft",
            preview: null,
            busy: false,
        });
    }

    async createDraft() {
        const question = this.state.question.trim();
        if (!question) {
            return;
        }
        this.state.busy = true;
        try {
            const result = await rpc("/ai_reporting/report_builder/create", { question });
            Object.assign(this.state, {
                requestId: result.id,
                status: result.state,
                preview: result.preview,
            });
        } catch (error) {
            this.notification.add(error.message || "Could not create the draft report.", { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    async adjustDraft() {
        const adjustment = this.state.adjustment.trim();
        if (!this.state.requestId || !adjustment) {
            return;
        }
        this.state.busy = true;
        try {
            const result = await rpc("/ai_reporting/report_builder/adjust", {
                request_id: this.state.requestId,
                adjustment,
            });
            Object.assign(this.state, {
                status: result.state,
                preview: result.preview,
                adjustment: "",
            });
        } catch (error) {
            this.notification.add(error.message || "Could not adjust the draft report.", { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    async confirmDraft() {
        if (!this.state.requestId) {
            return;
        }
        this.state.busy = true;
        try {
            const result = await rpc("/ai_reporting/report_builder/confirm", {
                request_id: this.state.requestId,
                name: this.state.question.slice(0, 80),
            });
            Object.assign(this.state, {
                status: result.state,
                savedReportId: result.saved_report_id,
            });
            this.notification.add("Advanced report saved.", { type: "success" });
        } catch (error) {
            this.notification.add(error.message || "Could not save the report.", { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("ai_reporting_report_builder", AiReportingReportBuilder);

