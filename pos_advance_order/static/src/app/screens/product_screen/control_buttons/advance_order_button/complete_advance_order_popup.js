/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { getAdvanceEligiblePaymentMethods } from "./advance_order_form_popup";
import {
    buildPaymentLines,
    initPaymentAmounts,
    parsePaymentAmount,
    validatePaymentLinesTotal,
    allocatedTotalFmt,
} from "@pos_advance_order/js/advance_payment_utils";

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

        this.state = useState({
            loading: true,
            search: "",
            selected_order_id: null,
            amount_tendered: 0,
            advance_orders: [],
            payment_methods: paymentMethods,
            payment_amounts: initPaymentAmounts(paymentMethods, 0),
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

    get popupTitle() {
        return this._tr("Complete Advance Order", "إكمال طلب العربون");
    }

    get popupSubtitle() {
        return this._tr("Pick an advance paid order to finish settlement", "اختر طلب عربون مدفوع لإكمال التسوية");
    }

    get searchLabel() {
        return this._tr("Search by Customer Name or Phone", "بحث باسم العميل أو رقم الهاتف");
    }

    get searchPlaceholder() {
        return this._tr("Type customer name or phone...", "اكتب اسم العميل أو رقم الهاتف...");
    }

    get amountTenderedLabel() {
        return this._tr("Amount Tendered", "المبلغ المستلم");
    }

    get amountTenderedHint() {
        return this._tr(
            "Customer paid amount for remaining settlement.",
            "المبلغ الذي دفعه العميل عند تسوية المتبقي."
        );
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

    get colAdvancePaidLabel() {
        return this._tr("Advance Paid", "العربون المدفوع");
    }

    get colRemainingLabel() {
        return this._tr("Remaining", "المتبقي");
    }

    get noOrdersText() {
        return this._tr("No advance orders found for this Picking POS.", "لا توجد طلبات عربون لنقطة الاستلام هذه.");
    }

    get paymentSplitHint() {
        return this._tr(
            "Split the remaining balance across one or more payment methods.",
            "قسّم المبلغ المتبقي على طريقة دفع أو أكثر."
        );
    }

    get allocatedLabel() {
        return this._tr("Allocated:", "المخصص:");
    }

    get paymentLines() {
        return buildPaymentLines(this.state.payment_methods, this.state.payment_amounts);
    }

    allocatedTotalFmt() {
        return allocatedTotalFmt(
            this.state.payment_methods,
            this.state.payment_amounts,
            this.props.pos?.currency?.id,
            formatCurrency
        );
    }

    paymentAllocationValid() {
        const due = this.selectedRemainingAmount;
        if (due <= 0) {
            return false;
        }
        return !validatePaymentLinesTotal(this.paymentLines, due);
    }

    get cancelButtonLabel() {
        return this._tr("Cancel", "إلغاء");
    }

    get completeButtonLabel() {
        return this._tr("Complete", "إكمال");
    }

    get changeReturnedLabel() {
        return this._tr("Change Returned", "المبلغ المرجّع");
    }

    get selectedRemainingAmount() {
        const sel = this.state.advance_orders.find((o) => o.id === this.state.selected_order_id);
        return Number(sel?.amount_remaining ?? 0);
    }

    get remainingChangeAmount() {
        const tendered = Number(this.state.amount_tendered || 0);
        const due = this.selectedRemainingAmount;
        return Math.max(tendered - due, 0);
    }

    isPaymentSelected(pm) {
        return parsePaymentAmount(this.state.payment_amounts[pm.id]) > 0;
    }

    paymentMethodRowClass(pm) {
        const selected = this.isPaymentSelected(pm);
        return (
            `paymentmethod d-flex justify-content-between align-items-center flex-fill text-start gap-2 ${selected ? "border border-2 border-primary rounded px-2 py-1" : "opacity-75"}`
        );
    }

    onPaymentAmountInput(pm, ev) {
        this.state.payment_amounts = {
            ...this.state.payment_amounts,
            [pm.id]: ev.target.value,
        };
    }

    onPaymentAmountBlur(pm) {
        const amount = parsePaymentAmount(this.state.payment_amounts[pm.id]);
        this.state.payment_amounts = {
            ...this.state.payment_amounts,
            [pm.id]: amount > 0 ? String(amount) : "0",
        };
    }

    _syncPaymentAmountsToRemaining() {
        const remaining = this.selectedRemainingAmount;
        if (remaining > 0) {
            this.state.payment_amounts = initPaymentAmounts(this.state.payment_methods, remaining);
        }
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
                error?.message || this._tr("Failed to load advance orders.", "فشل تحميل طلبات العربون."),
                { type: "danger" }
            );
        }
    }

    get noEligiblePaymentMethodsText() {
        return this._tr(
            "No eligible payment methods on this POS. Add manual cash or bank methods without terminal or QR integration in the Point of Sale configuration.",
            "لا توجد طرق دفع مناسبة في نقطة البيع هذه. أضف طرق دفع نقدية أو بنكية يدوية بدون تكامل طرفية أو QR في إعدادات نقطة البيع."
        );
    }

    onSearchInput(ev) {
        this.state.search = (ev.target.value || "").toLowerCase();
    }

    onAmountTenderedInput(ev) {
        const value = Number(ev.target.value || 0);
        this.state.amount_tendered = Number.isFinite(value) ? value : 0;
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
        const selected = this.state.advance_orders.find((o) => o.id === orderId);
        const remaining = Number(selected?.amount_remaining ?? 0);
        this.state.amount_tendered = remaining;
        this.state.payment_amounts = initPaymentAmounts(this.state.payment_methods, remaining);
    }

    confirm() {
        if (!this.state.selected_order_id) {
            this.notification.add(this._tr("Please select an advance order.", "يرجى اختيار طلب عربون."), { type: "warning" });
            return;
        }
        const paymentLines = this.paymentLines;
        const allocationError = validatePaymentLinesTotal(
            paymentLines,
            this.selectedRemainingAmount
        );
        if (allocationError) {
            this.notification.add(allocationError, { type: "warning" });
            return;
        }
        if (this.state.amount_tendered < this.selectedRemainingAmount) {
            this.notification.add(
                this._tr("Amount tendered cannot be less than remaining amount.", "لا يمكن أن يكون المبلغ المستلم أقل من المبلغ المتبقي."),
                { type: "warning" }
            );
            return;
        }
        const primaryPm = paymentLines[0];
        this.props.getPayload({
            advance_order_id: this.state.selected_order_id,
            payment_method_id: primaryPm.payment_method_id,
            payment_method_name: primaryPm.payment_method_name || "",
            payment_lines: paymentLines.map((line) => ({
                payment_method_id: line.payment_method_id,
                amount: line.amount,
            })),
            amount_tendered: this.state.amount_tendered,
            change_amount: this.remainingChangeAmount,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
