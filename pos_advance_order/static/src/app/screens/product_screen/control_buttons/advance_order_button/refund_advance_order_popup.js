/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";

export class RefundAdvanceOrderPopup extends Component {
    static template = "pos_advance_order.RefundAdvanceOrderPopup";
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

        this.state = useState({
            loading: true,
            search: "",
            selected_order_id: null,
            advance_orders: [],
        });

        onMounted(async () => {
            await this._loadAdvanceOrders();
            this.state.loading = false;
        });
    }

    _isArabicContext() {
        const urlLang = new URLSearchParams(window.location.search).get("lang") || "";
        const htmlLang = document?.documentElement?.lang || "";
        const bodyDir = document?.body ? window.getComputedStyle(document.body).direction : "";
        return urlLang.startsWith("ar") || htmlLang.startsWith("ar") || bodyDir === "rtl";
    }

    _tr(msgid, fallbackArabic) {
        const translated = _t(msgid);
        if (translated === msgid && this._isArabicContext()) {
            return fallbackArabic;
        }
        return translated;
    }

    get popupTitle() {
        return this._tr("Refund Advance", "استرداد العربون");
    }

    get popupSubtitle() {
        return this._tr(
            "Select an advance order to return the deposit to the customer",
            "اختر طلب عربون لإرجاع العربون للعميل"
        );
    }

    get searchLabel() {
        return this._tr("Search by Customer Name or Phone", "بحث باسم العميل أو رقم الهاتف");
    }

    get searchPlaceholder() {
        return this._tr("Type customer name or phone...", "اكتب اسم العميل أو رقم الهاتف...");
    }

    get colAdvanceLabel() {
        return this._tr("Advance", "العربون");
    }

    get colCustomerLabel() {
        return this._tr("Customer", "العميل");
    }

    get colPhoneLabel() {
        return this._tr("Phone", "الهاتف");
    }

    get colTotalLabel() {
        return this._tr("Total", "الإجمالي");
    }

    get colRefundLabel() {
        return this._tr("Refund Amount", "مبلغ الاسترداد");
    }

    get colPickingPosLabel() {
        return this._tr("Picking POS", "نقطة الاستلام");
    }

    get noOrdersText() {
        return this._tr(
            "No refundable advance orders found for this POS.",
            "لا توجد طلبات عربون قابلة للاسترداد في نقطة البيع هذه."
        );
    }

    get cancelButtonLabel() {
        return this._tr("Cancel", "إلغاء");
    }

    get refundButtonLabel() {
        return this._tr("Refund", "استرداد");
    }

    get selectedRefundAmountFmt() {
        const currencyId = this.props.pos?.currency?.id;
        const sel = this.state.advance_orders.find((o) => o.id === this.state.selected_order_id);
        const amount = sel ? Number(sel.advance_amount ?? 0) : 0;
        return formatCurrency(amount, currencyId);
    }

    get refundHintText() {
        return this._tr(
            "The deposit will be returned using the original payment method. The order will be cancelled.",
            "سيتم إرجاع العربون بنفس طريقة الدفع الأصلية وسيتم إلغاء الطلب."
        );
    }

    async _loadAdvanceOrders() {
        try {
            const posConfigId = this.props.posConfigId;
            const domain = [
                ["state", "=", "advance_paid"],
                ["remaining_pos_order_id", "=", false],
                ["refund_advance_pos_order_id", "=", false],
                ["advance_refund_move_id", "=", false],
                ["advance_payment_created", "=", true],
                "|",
                ["from_pos_config_id", "=", posConfigId],
                "&",
                ["from_pos_config_id", "=", false],
                ["pos_config_id", "=", posConfigId],
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
                    "picking_date",
                    "pos_config_id",
                    "pos_payment_method_id",
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
                payment_method_name: order.pos_payment_method_id?.[1] || "",
            }));
        } catch (error) {
            this.notification.add(
                error?.message || this._tr("Failed to load advance orders.", "فشل تحميل طلبات العربون."),
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
            const reference = (order.name || "").toLowerCase();
            return (
                customerName.includes(term) ||
                customerPhone.includes(term) ||
                reference.includes(term)
            );
        });
    }

    selectOrder(orderId) {
        this.state.selected_order_id = orderId;
    }

    confirm() {
        if (!this.state.selected_order_id) {
            this.notification.add(
                this._tr("Please select an advance order.", "يرجى اختيار طلب عربون."),
                { type: "warning" }
            );
            return;
        }
        const selected = this.state.advance_orders.find((o) => o.id === this.state.selected_order_id);
        this.props.getPayload({
            advance_order_id: this.state.selected_order_id,
            advance_amount: Number(selected?.advance_amount ?? 0),
            payment_method_name: selected?.payment_method_name || "",
            partner_name: selected?.partner_id?.[1] || "",
            partner_phone: selected?.partner_phone || "",
            reference: selected?.name || "",
            amount_total: Number(selected?.amount_total ?? 0),
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
