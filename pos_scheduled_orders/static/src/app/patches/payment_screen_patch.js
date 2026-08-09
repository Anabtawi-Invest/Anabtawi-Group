/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        const order = this.currentOrder || this.pos?.get_order?.() || this.pos?.selectedOrder;
        const posConfig = this.pos?.config;

        if (posConfig?.enable_fulfillment_schedule && order?.fulfillment_type) {
            const data = order.getFulfillmentData?.() || {};

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

            // Check Partial Payment Deposit Status
            const due = order.get_due?.() || 0;
            const total = order.get_total_with_tax?.() || 0;

            if (due > 0 && due < total) {
                order.setFulfillmentData?.({
                    is_advance_deposit: true,
                    jofotara_status: "pending",
                });
            } else if (due <= 0) {
                order.setFulfillmentData?.({
                    is_advance_deposit: false,
                    jofotara_status: "submitted",
                });
            }
        }

        return await super.validateOrder(...arguments);
    },
});
