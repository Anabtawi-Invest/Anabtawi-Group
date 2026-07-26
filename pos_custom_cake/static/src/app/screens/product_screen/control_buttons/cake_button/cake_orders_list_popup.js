/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { rpc } from "@web/core/network/rpc";

export class CakeOrdersListPopup extends Component {
    static template = "pos_custom_cake.CakeOrdersListPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        pos: Object,
    };

    setup() {
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            query: "",
            orders: [],
        });
        onMounted(async () => {
            await this._searchOrders();
            this.state.loading = false;
        });
    }

    get dialogTitle() {
        return `🎂 ${_t("Cake Orders")}`;
    }

    get labels() {
        return {
            searchPlaceholder: _t("Search by customer name or order number..."),
            noOrders: _t("No cake orders waiting for payment."),
            orderNumber: _t("Order Number"),
            customer: _t("Customer"),
            cakePieces: _t("Cake Pieces"),
            status: _t("Status"),
            date: _t("Date"),
            finalPrice: _t("Final Price"),
            close: _t("Close"),
        };
    }

    formatAmount(amount) {
        return formatCurrency(amount || 0, this.props.pos.currency?.id);
    }

    formatDate(dateStr) {
        if (!dateStr) {
            return "";
        }
        try {
            return new Date(dateStr).toLocaleString();
        } catch {
            return dateStr;
        }
    }

    getStateLabel(state) {
        const labels = {
            waiting_payment: _t("Waiting for Payment"),
            paid: _t("Paid"),
            cancelled: _t("Cancelled"),
            draft: _t("Draft"),
        };
        return labels[state] || state;
    }

    async _searchOrders() {
        try {
            this.state.loading = true;
            const orders = await rpc("/pos/custom_cake/search_orders", {
                query: this.state.query,
                limit: 50,
            });
            this.state.orders = orders || [];
        } catch (error) {
            this.notification.add(error?.message || _t("Failed to load cake orders."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.query = ev.target.value || "";
    }

    async onSearch() {
        await this._searchOrders();
    }

    async onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            await this._searchOrders();
        }
    }

    selectOrder(order) {
        this.props.getPayload({ order });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
