/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";

patch(OrderReceipt.prototype, {
    get fulfillmentInfo() {
        const order = this.props.order || this.pos?.getOrder?.();
        if (!order) {
            return null;
        }
        const fType = order.fulfillment_type;
        if (!fType) {
            return null;
        }

        let scheduledFmt = order.scheduled_datetime || "";
        if (scheduledFmt) {
            try {
                const d = new Date(scheduledFmt);
                scheduledFmt = d.toLocaleString();
            } catch (e) {
                // fallback
            }
        }

        let fullAddress = [
            order.delivery_street,
            order.delivery_city,
            order.delivery_building_apt,
            order.delivery_zip
        ].filter(Boolean).join(", ");

        const due = order.get_due?.() || 0;
        const total = order.get_total_with_tax?.() || 0;
        const paid = Math.max(total - due, 0);

        return {
            typeLabel: fType === "pickup" ? "استلام من الفرع (STORE PICKUP)" : "توصيل منزلي (HOME DELIVERY)",
            isPickup: fType === "pickup",
            isDelivery: fType === "delivery",
            scheduledTime: scheduledFmt,
            contactName: order.delivery_address_name || "",
            contactPhone: order.delivery_address_phone || "",
            address: fullAddress,
            isCatering: !!order.is_catering,
            isAdvanceDeposit: !!order.is_advance_deposit || (due > 0 && paid > 0),
            depositPaidAmount: paid,
            outstandingBalanceDue: due,
        };
    },
});
