/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";

export class CompleteScheduleModal extends Component {
    static template = "pos_scheduled_orders.CompleteScheduleModal";
    static components = { Dialog };
    static props = {
        close: Function,
        pos: Object,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        const paymentMethods = this.props.pos?.payment_methods || [];
        const defaultPmId = paymentMethods.length ? paymentMethods[0].id : null;

        this.state = useState({
            loading: true,
            searchQuery: "",
            orders: [],
            selectedOrderId: null,
            payment_methods: paymentMethods,
            selectedPaymentMethodId: defaultPmId,
            amountTendered: 0,
            error_message: "",
        });

        onMounted(async () => {
            await this.loadOpenOrders();
        });
    }

    async loadOpenOrders() {
        this.state.loading = true;
        this.state.error_message = "";
        try {
            const posConfigId = this.props.pos?.config?.id;
            const res = await this.orm.call(
                "pos.order",
                "search_open_scheduled_orders",
                [posConfigId, this.state.searchQuery]
            );
            this.state.orders = res || [];
            if (this.state.orders.length > 0 && !this.state.selectedOrderId) {
                this.selectOrder(this.state.orders[0]);
            }
        } catch (e) {
            console.error("Error loading open scheduled orders:", e);
            this.state.error_message = _t("فشل تحميل طلبات التواصي المعلقة.");
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
        this.loadOpenOrders();
    }

    selectOrder(order) {
        this.state.selectedOrderId = order.id;
        this.state.amountTendered = order.amount_due;
        this.state.error_message = "";
    }

    selectPaymentMethod(pmId) {
        this.state.selectedPaymentMethodId = pmId;
    }

    get selectedOrder() {
        return this.state.orders.find((o) => o.id === this.state.selectedOrderId) || null;
    }

    async confirmSettlement() {
        const order = this.selectedOrder;
        if (!order) {
            this.state.error_message = _t("يرجى اختيار طلب تواصي لاستكمال السداد.");
            return;
        }

        if (!this.state.selectedPaymentMethodId) {
            this.state.error_message = _t("يرجى اختيار طريقة الدفع (كاش أو فيزا).");
            return;
        }

        this.state.loading = true;
        try {
            const res = await this.orm.call(
                "pos.order",
                "action_complete_scheduled_order_from_pos",
                [order.id, this.state.selectedPaymentMethodId, this.state.amountTendered]
            );

            if (res && res.success) {
                this.notification.add(
                    _t("تم استكمال سداد الطلب %s وترحيل المخزون وإصدار الفاتورة الضريبية بنجاح.", res.name),
                    { type: "success" }
                );
                this.props.close();
            } else {
                this.state.error_message = _t("فشلت عملية استكمال الطلب.");
            }
        } catch (e) {
            const msg = e?.data?.message || e?.message || _t("حدث خطأ أثناء استكمال الطلب.");
            this.state.error_message = msg;
        } finally {
            this.state.loading = false;
        }
    }

    cancel() {
        this.props.close();
    }
}

patch(ControlButtons.prototype, {
    async onClickCompleteSchedule() {
        this.dialog.add(CompleteScheduleModal, {
            pos: this.pos,
        });
    },
});
