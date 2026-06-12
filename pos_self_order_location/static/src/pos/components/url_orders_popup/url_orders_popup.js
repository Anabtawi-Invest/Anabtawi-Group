/** @odoo-module */

import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

export class UrlOrdersPopup extends Component {
    static template = "pos_self_order_location.UrlOrdersPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: { type: Function, optional: true },
    };

    setup() {
        this.pos = usePos();
        this.state = useState({
            loading: true,
            requests: [],
        });

        onWillStart(async () => {
            await this.loadRequests();
        });
    }

    async loadRequests() {
        this.state.loading = true;
        try {
            this.state.requests = await this.pos.data.call(
                "pos.self.order.request",
                "get_open_requests",
                [this.pos.config.id]
            );
        } catch (error) {
            this.pos.notification.add(_t("Could not load URL self-orders."), { type: "danger" });
            this.state.requests = [];
        } finally {
            this.state.loading = false;
        }
    }

    formatAmount(request) {
        return this.pos.env.utils.formatCurrency(request.amount_total);
    }

    formatState(state) {
        const labels = {
            new: _t("New"),
            accepted: _t("Accepted"),
            done: _t("Done"),
            cancelled: _t("Cancelled"),
        };
        return labels[state] || state;
    }

    formatPaymentBadge(request) {
        if (request.payment_preference_label) {
            return request.payment_preference_label;
        }
        if (request.payment_preference === "cash_on_delivery") {
            return _t("Cash on delivery");
        }
        if (request.payment_preference === "online_card") {
            return request.pos_order_state === "paid" ? _t("Card (Paid)") : _t("Card (Unpaid)");
        }
        return "";
    }

    formatPaymentBadgeClass(request) {
        if (request.payment_preference === "cash_on_delivery") {
            return "text-bg-warning";
        }
        if (request.payment_preference === "online_card") {
            return request.pos_order_state === "paid" ? "text-bg-success" : "text-bg-info";
        }
        return "text-bg-light";
    }

    openMap(request) {
        if (request.location_url) {
            window.open(request.location_url, "_blank");
        }
    }

    async updateRequestState(request, method) {
        try {
            await this.pos.data.call("pos.self.order.request", method, [[request.id]]);
            await this.loadRequests();
        } catch (error) {
            this.pos.notification.add(_t("Could not update the request."), { type: "danger" });
        }
    }

    async acceptRequest(request) {
        await this.updateRequestState(request, "action_mark_accepted");
    }

    async doneRequest(request) {
        await this.updateRequestState(request, "action_mark_done");
    }
}
