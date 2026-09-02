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
            detailLoading: false,
            view: "list", // "list" | "detail"
            search: "",
            selected_order_id: null,
            amount_tendered: 0,
            advance_orders: [],
            detail_lines: [],
            detail_pledges: [],
            payment_methods: paymentMethods,
            selected_payment_method_id: defaultPmId,
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

    _fmtMoney(amount) {
        const currencyId = this.props.pos?.currency?.id;
        return formatCurrency(Number(amount || 0), currencyId);
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
        return this._fmtMoney(this.selectedRemainingAmount);
    }

    get popupTitle() {
        if (this.state.view === "detail") {
            return this._tr("Advance Order Details", "تفاصيل طلب العربون");
        }
        return this._tr("Complete Advance Order", "إكمال طلب العربون");
    }

    get popupSubtitle() {
        if (this.state.view === "detail") {
            return this._tr(
                "Review products and settle the remaining balance.",
                "راجع المنتجات وسوِّ المبلغ المتبقي."
            );
        }
        return this._tr(
            "Pick an advance paid order to finish settlement",
            "اختر طلب عربون مدفوع لإكمال التسوية"
        );
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

    get colProductLabel() {
        return this._tr("Product", "المنتج");
    }

    get colQtyLabel() {
        return this._tr("Qty", "الكمية");
    }

    get colUnitPriceLabel() {
        return this._tr("Unit Price", "سعر الوحدة");
    }

    get colSubtotalLabel() {
        return this._tr("Subtotal", "المجموع الفرعي");
    }

    get colDiscountPctLabel() {
        return this._tr("Disc %", "خصم %");
    }

    get linesSectionLabel() {
        return this._tr("Order Lines", "بنود الطلب");
    }

    get pledgesSectionLabel() {
        return this._tr("Pledges", "العهد");
    }

    get noLinesText() {
        return this._tr("No product lines on this order.", "لا توجد بنود منتجات في هذا الطلب.");
    }

    get noPledgesText() {
        return this._tr("No pledges on this order.", "لا توجد عهد على هذا الطلب.");
    }

    get siteServiceLabel() {
        return this._tr("Site Service", "خدمة الموقع");
    }

    get siteServiceYesLabel() {
        return this._tr("Yes", "نعم");
    }

    get siteServiceNoLabel() {
        return this._tr("No", "لا");
    }

    get discountLabel() {
        return this._tr("Discount", "الخصم");
    }

    get pledgeAmountLabel() {
        return this._tr("Pledge Amount", "مبلغ العهد");
    }

    get pickingDateLabel() {
        return this._tr("Picking Date", "تاريخ الاستلام");
    }

    get noOrdersText() {
        return this._tr(
            "No advance orders found for this Picking POS.",
            "لا توجد طلبات عربون لنقطة الاستلام هذه."
        );
    }

    get paymentMethodLabel() {
        return this._tr("Payment method", "طريقة الدفع");
    }

    get cancelButtonLabel() {
        return this._tr("Cancel", "إلغاء");
    }

    get backButtonLabel() {
        return this._tr("Back", "رجوع");
    }

    get nextButtonLabel() {
        return this._tr("Next", "التالي");
    }

    get completeButtonLabel() {
        return this._tr("Complete", "إكمال");
    }

    get changeReturnedLabel() {
        return this._tr("Change Returned", "المبلغ المرجّع");
    }

    get selectedOrder() {
        return this.state.advance_orders.find((o) => o.id === this.state.selected_order_id) || null;
    }

    get selectedRemainingAmount() {
        return Number(this.selectedOrder?.amount_remaining ?? 0);
    }

    get remainingChangeAmount() {
        const tendered = Number(this.state.amount_tendered || 0);
        const due = this.selectedRemainingAmount;
        return Math.max(tendered - due, 0);
    }

    get discountDisplayName() {
        const order = this.selectedOrder;
        if (!order) {
            return "";
        }
        const name = order.discount_id?.[1] || "";
        const amount = Number(order.discount_amount || 0);
        if (name && amount) {
            return `${name} (${this._fmtMoney(amount)})`;
        }
        if (name) {
            return name;
        }
        if (amount) {
            return this._fmtMoney(amount);
        }
        return this._tr("None", "لا يوجد");
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
                    "site_service",
                    "discount_id",
                    "discount_amount",
                    "pledge_amount",
                    "pledge_count",
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

    async _loadOrderDetail(orderId) {
        this.state.detailLoading = true;
        this.state.detail_lines = [];
        this.state.detail_pledges = [];
        try {
            const [lines, pledges] = await Promise.all([
                this.orm.searchRead(
                    "pos.advance.order.line",
                    [["order_id", "=", orderId]],
                    [
                        "id",
                        "product_id",
                        "product_qty",
                        "price_unit",
                        "discount",
                        "price_subtotal_incl",
                        "display_type",
                        "sequence",
                    ],
                    { order: "sequence, id" }
                ),
                this.orm.searchRead(
                    "pos.advance.order.pledge",
                    [["order_id", "=", orderId]],
                    [
                        "id",
                        "product_id",
                        "source_product_id",
                        "pledge_qty",
                        "pledge_amount_unit",
                        "pledge_subtotal",
                        "state",
                    ],
                    { order: "id" }
                ),
            ]);
            this.state.detail_lines = (lines || []).filter(
                (line) => !line.display_type && line.product_id
            );
            this.state.detail_pledges = pledges || [];
        } catch (error) {
            this.notification.add(
                error?.message ||
                    this._tr("Failed to load advance order details.", "فشل تحميل تفاصيل طلب العربون."),
                { type: "danger" }
            );
            throw error;
        } finally {
            this.state.detailLoading = false;
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
        this.state.amount_tendered = Number(selected?.amount_remaining ?? 0);
    }

    async goToDetail() {
        if (!this.state.selected_order_id) {
            this.notification.add(
                this._tr("Please select an advance order.", "يرجى اختيار طلب عربون."),
                { type: "warning" }
            );
            return;
        }
        try {
            await this._loadOrderDetail(this.state.selected_order_id);
            this.state.view = "detail";
        } catch {
            // notification already shown in _loadOrderDetail
        }
    }

    goBackToList() {
        this.state.view = "list";
        this.state.detail_lines = [];
        this.state.detail_pledges = [];
    }

    confirm() {
        if (!this.state.selected_order_id) {
            this.notification.add(
                this._tr("Please select an advance order.", "يرجى اختيار طلب عربون."),
                { type: "warning" }
            );
            return;
        }
        if (!this.state.selected_payment_method_id) {
            this.notification.add(
                this._tr("Please select a payment method.", "يرجى اختيار طريقة دفع."),
                { type: "warning" }
            );
            return;
        }
        if (this.state.amount_tendered < this.selectedRemainingAmount) {
            this.notification.add(
                this._tr(
                    "Amount tendered cannot be less than remaining amount.",
                    "لا يمكن أن يكون المبلغ المستلم أقل من المبلغ المتبقي."
                ),
                { type: "warning" }
            );
            return;
        }
        const selectedPm = this.state.payment_methods.find(
            (pm) => pm.id === this.state.selected_payment_method_id
        );
        this.props.getPayload({
            advance_order_id: this.state.selected_order_id,
            payment_method_id: this.state.selected_payment_method_id,
            payment_method_name: selectedPm?.name || "",
            amount_tendered: this.state.amount_tendered,
            change_amount: this.remainingChangeAmount,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
