/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

export class ScheduledOrdersListModal extends Component {
    static template = "pos_scheduled_orders.ScheduledOrdersListModal";
    static components = { Dialog };
    static props = {
        close: Function,
        pos: Object,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            searchQuery: "",
            orders: [],
            selectedOrderId: null,
            error_message: "",
        });

        onMounted(async () => {
            await this.loadScheduledOrders();
        });
    }

    async loadScheduledOrders() {
        this.state.loading = true;
        this.state.error_message = "";
        try {
            if (typeof this.props.pos?.push_orders === "function") {
                try {
                    await this.props.pos.push_orders();
                } catch (pushErr) {
                    console.warn("Notice: push_orders sync:", pushErr);
                }
            }

            const config = this.props.pos?.config || {};
            const posConfigId = parseInt(config.id || (Array.isArray(config) ? config[0] : 0) || 0);
            const searchQuery = String(this.state.searchQuery || "");

            const currentOrder = this.props.pos?.get_order?.();
            const partner = currentOrder?.getPartner?.() || currentOrder?.get_partner?.() || currentOrder?.partner;
            const partnerId = partner ? partner.id : false;

            const res = await this.orm.call(
                "pos.order",
                "search_open_scheduled_orders",
                [posConfigId, searchQuery, partnerId]
            );
            this.state.orders = res || [];
            if (this.state.orders.length > 0 && !this.state.selectedOrderId) {
                this.state.selectedOrderId = this.state.orders[0].id;
            }
        } catch (e) {
            console.error("Error loading scheduled orders list:", e);
            const msg = e?.data?.message || e?.message || _t("فشل تحميل قائمة طلبيات التواصي.");
            this.state.error_message = msg;
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
        this.loadScheduledOrders();
    }

    selectOrder(order) {
        this.state.selectedOrderId = order.id;
        this.state.error_message = "";
    }

    get selectedOrder() {
        return this.state.orders.find((o) => o.id === this.state.selectedOrderId) || null;
    }

    async loadOrderToPOS(order) {
        if (!order) return;
        this.state.loading = true;
        try {
            // Find or create customer
            let partner = null;
            if (order.partner_id) {
                partner = this.props.pos.db.get_partner_by_id(order.partner_id);
            }

            const posOrder = this.props.pos.get_order() || this.props.pos.add_new_order();
            if (partner && posOrder) {
                if (typeof posOrder.setPartner === "function") {
                    posOrder.setPartner(partner);
                } else if (typeof posOrder.set_partner === "function") {
                    posOrder.set_partner(partner);
                } else {
                    posOrder.partner = partner;
                }
            }

            if (posOrder) {
                posOrder.fulfillment_type = order.fulfillment_type || "pickup";
                posOrder.scheduled_datetime = order.scheduled_datetime || "";
                posOrder.delivery_address_name = order.customer_name || "";
                posOrder.delivery_address_phone = order.customer_phone || "";
                posOrder.delivery_street = order.street || "";
                posOrder.delivery_city = order.city || "";
                posOrder.advance_order_id = order.id;
                posOrder.advance_payment_amount = order.amount_paid || 0;
                posOrder.is_advance_deposit = true;
            }

            this.notification.add(
                _t("تم تحميل الطلب %s بنجاح. يرجى استكمال سداد المتبقي.", order.name),
                { type: "success" }
            );

            this.props.close();

            // Direct transition to PaymentScreen
            if (typeof this.props.pos.showScreen === "function") {
                this.props.pos.showScreen("PaymentScreen");
            }
        } catch (e) {
            console.error("Error loading order to POS:", e);
            this.state.error_message = _t("حدث خطأ أثناء تحميل الطلب على شاشة الكاشير.");
        } finally {
            this.state.loading = false;
        }
    }

    cancel() {
        this.props.close();
    }
}

patch(ControlButtons.prototype, {
    async onClickScheduledOrdersList() {
        this.dialog.add(ScheduledOrdersListModal, {
            pos: this.pos,
        });
    },
});
