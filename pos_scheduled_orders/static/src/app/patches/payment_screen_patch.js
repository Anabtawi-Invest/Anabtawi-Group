/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

function getOrderPartner(order) {
    if (!order) return null;
    if (typeof order.getPartner === "function") {
        const p = order.getPartner();
        if (p) return p;
    }
    if (typeof order.get_partner === "function") {
        const p = order.get_partner();
        if (p) return p;
    }
    if (order.partner) return order.partner;
    if (order.customer) return order.customer;
    if (order.partner_id) return order.partner_id;
    return null;
}

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        const order = this.currentOrder || this.pos?.get_order?.() || this.pos?.selectedOrder;
        const posConfig = this.pos?.config;

        if (posConfig?.enable_fulfillment_schedule && order?.fulfillment_type) {
            const data = order.getFulfillmentData?.() || {};

            // Enforce Customer DB Partner Linking (res.partner required for credit sales / ذمم)
            const partner = getOrderPartner(order);
            if (!partner) {
                this.dialog.add(AlertDialog, {
                    title: _t("Validation Error: Customer Required"),
                    body: _t("يجب تحديد أو اختيار عميل مسجل بالنظام لإكمال طلب التواصي والمبيعات الآجلة (ذمم). يرجى فتح نافذة 'طلبيات تواصي' واختيار العميل."),
                });
                return false;
            }

            // Mandatory Validation Checks
            if (!data.delivery_address_name || !data.delivery_address_name.trim()) {
                this.dialog.add(AlertDialog, {
                    title: _t("Validation Error: Customer Name Required"),
                    body: _t("اسم العميل مطلوب لإكمال طلب التواصي / التوصيل. يرجى الضغط على زر 'طلبيات تواصي' لتعبئة البيانات."),
                });
                return false;
            }

            if (!data.delivery_address_phone || !data.delivery_address_phone.trim()) {
                this.dialog.add(AlertDialog, {
                    title: _t("Validation Error: Customer Mobile Required"),
                    body: _t("رقم هاتف العميل مطلوب لإكمال طلب التواصي / التوصيل. يرجى الضغط على زر 'طلبيات تواصي' لتعبئة البيانات."),
                });
                return false;
            }

            if (!data.scheduled_datetime) {
                this.dialog.add(AlertDialog, {
                    title: _t("Validation Error: Scheduled Date & Time Required"),
                    body: _t("تاريخ وموعد الاستلام / التوصيل مطلوب. يرجى تحديد الموعد من زر 'طلبيات تواصي'."),
                });
                return false;
            }

            if (data.fulfillment_type === "delivery") {
                if (!data.delivery_street && !data.delivery_city) {
                    this.dialog.add(AlertDialog, {
                        title: _t("Validation Error: Delivery Address Required"),
                        body: _t("عنوان التوصيل التفصيلي (الشارع والمدينة) إجباري لطلبات التوصيل المنزلي."),
                    });
                    return false;
                }
            }

            // Check Partial Deposit (Cash/Visa) & Credit Sales (مبيعات ذمم) Status
            const due = order.get_due?.() || 0;
            const total = order.get_total_with_tax?.() || 0;
            const paid = order.get_total_paid?.() || (total - due);

            if (due > 0 && paid > 0) {
                // Partial deposit paid (Cash or Visa), remaining balance posted on Customer Account (ذمم)
                order.setFulfillmentData?.({
                    is_advance_deposit: true,
                    jofotara_status: "pending",
                });
            } else if (due <= 0) {
                // Fully settled order
                order.setFulfillmentData?.({
                    is_advance_deposit: false,
                    jofotara_status: "submitted",
                });
            }
        }

        return await super.validateOrder(...arguments);
    },
});
