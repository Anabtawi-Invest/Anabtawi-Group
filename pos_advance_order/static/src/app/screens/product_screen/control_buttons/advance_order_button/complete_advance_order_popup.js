/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export class CompleteAdvanceOrderPopup extends Component {
    static template = "pos_advance_order.CompleteAdvanceOrderPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        posConfigId: { type: Number, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            search: "",
            selected_order_id: null,
            payment_method: "cash",
            advance_orders: [],
        });

        onMounted(async () => {
            await this._loadAdvanceOrders();
            this.state.loading = false;
        });
    }

    async _loadAdvanceOrders() {
        try {
            const domain = [
                ["state", "=", "advance_paid"],
                ["pos_config_id", "=", this.props.posConfigId],
                ["remaining_pos_order_id", "=", false],
            ];
            const orders = await this.orm.searchRead(
                "pos.advance.order",
                domain,
                [
                    "id",
                    "name",
                    "partner_id",
                    "amount_total",
                    "advance_amount",
                    "amount_remaining",
                    "picking_date",
                ],
                { limit: 500, order: "id desc" }
            );
            const partnerIds = [...new Set((orders || []).map((o) => o.partner_id?.[0]).filter(Boolean))];
            let partnerPhoneById = {};
            if (partnerIds.length) {
                const partners = await this.orm.searchRead(
                    "res.partner",
                    [["id", "in", partnerIds]],
                    ["id", "phone"]
                );
                partnerPhoneById = (partners || []).reduce((acc, p) => {
                    acc[p.id] = p.phone || "";
                    return acc;
                }, {});
            }
            this.state.advance_orders = (orders || []).map((order) => ({
                ...order,
                partner_phone: partnerPhoneById[order.partner_id?.[0]] || "",
            }));
        } catch (error) {
            this.notification.add(
                error?.message || _t("Failed to load advance orders."),
                { type: "danger" }
            );
        }
    }

    onSearchInput(ev) {
        this.state.search = (ev.target.value || "").toLowerCase();
    }

    get filteredOrders() {
        const term = (this.state.search || "").trim();
        if (!term) {
            return this.state.advance_orders;
        }
        return this.state.advance_orders.filter((order) => {
            const customerName = (order.partner_id?.[1] || "").toLowerCase();
            const customerPhone = (order.partner_phone || "").toLowerCase();
            return customerName.includes(term) || customerPhone.includes(term);
        });
    }

    selectOrder(orderId) {
        this.state.selected_order_id = orderId;
    }

    onPaymentMethodChange(ev) {
        this.state.payment_method = ev.target.value || "cash";
    }

    confirm() {
        if (!this.state.selected_order_id) {
            this.notification.add(_t("Please select an advance order."), { type: "warning" });
            return;
        }
        this.props.getPayload({
            advance_order_id: this.state.selected_order_id,
            payment_method: this.state.payment_method,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}

