/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { getAdvanceEligiblePaymentMethods } from "./advance_order_form_popup";

export class CompleteAdvanceOrderPopup extends Component {
    static template = "pos_advance_order.CompleteAdvanceOrderPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        posConfigId: { type: Number, optional: true },
        pos: Object,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const paymentMethods = getAdvanceEligiblePaymentMethods(this.props.pos);
        const defaultPmId = paymentMethods.length ? paymentMethods[0].id : null;

        this.state = useState({
            loading: true,
            search: "",
            selected_order_id: null,
            advance_orders: [],
            payment_methods: paymentMethods,
            selected_payment_method_id: defaultPmId,
        });

        onMounted(async () => {
            await this._loadAdvanceOrders();
            this.state.loading = false;
        });
    }

    paymentMethodIconSrc(pm) {
        if (!pm) {
            return "";
        }
        if (pm.image) {
            return `/web/image/pos.payment.method/${pm.id}/image`;
        }
        if (pm.type === "cash") {
            return "/point_of_sale/static/src/img/money.png";
        }
        return "/point_of_sale/static/src/img/card-bank.png";
    }

    remainingAmountFmt() {
        const currencyId = this.props.pos?.currency?.id;
        const sel = this.state.advance_orders.find((o) => o.id === this.state.selected_order_id);
        const amount = sel ? Number(sel.amount_remaining ?? 0) : 0;
        return formatCurrency(amount, currencyId);
    }

    isPaymentSelected(pm) {
        return pm.id === this.state.selected_payment_method_id;
    }

    paymentMethodRowClass(pm) {
        const selected = this.isPaymentSelected(pm);
        return (
            `button paymentmethod btn btn-secondary btn-lg lh-lg d-flex justify-content-between align-items-center flex-fill text-start ${selected ? "border border-3 border-primary" : "opacity-75"}`
        );
    }

    selectPaymentMethod(pm) {
        this.state.selected_payment_method_id = pm.id;
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

    get noEligiblePaymentMethodsText() {
        return _t(
            "No eligible payment methods on this POS. Add manual cash or bank methods without terminal or QR integration in the Point of Sale configuration."
        );
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

    confirm() {
        if (!this.state.selected_order_id) {
            this.notification.add(_t("Please select an advance order."), { type: "warning" });
            return;
        }
        if (!this.state.selected_payment_method_id) {
            this.notification.add(_t("Please select a payment method."), { type: "warning" });
            return;
        }
        const selectedPm = this.state.payment_methods.find(
            (pm) => pm.id === this.state.selected_payment_method_id
        );
        this.props.getPayload({
            advance_order_id: this.state.selected_order_id,
            payment_method_id: this.state.selected_payment_method_id,
            payment_method_name: selectedPm?.name || "",
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
