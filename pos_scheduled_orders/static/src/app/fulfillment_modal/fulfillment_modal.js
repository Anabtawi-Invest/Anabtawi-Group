/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export class FulfillmentModal extends Component {
    static template = "pos_scheduled_orders.FulfillmentModal";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        pos: Object,
        order: Object,
    };

    setup() {
        this.notification = useService("notification");
        const order = this.props.order;
        const partner = order?.getPartner?.() || order?.partner || null;

        let initialDatetime = order.scheduled_datetime;
        if (!initialDatetime) {
            const now = new Date();
            now.setHours(now.getHours() + 2);
            now.setMinutes(0);
            initialDatetime = now.toISOString().slice(0, 16);
        } else if (typeof initialDatetime === "string" && initialDatetime.length > 16) {
            initialDatetime = initialDatetime.slice(0, 16);
        }

        this.state = useState({
            activeTab: order.fulfillment_type || "pickup",
            customer_name: order.delivery_address_name || partner?.name || "",
            mobile: order.delivery_address_phone || partner?.mobile || partner?.phone || "",
            scheduled_datetime: initialDatetime,
            street: order.delivery_street || partner?.street || "",
            city: order.delivery_city || partner?.city || "",
            zip: order.delivery_zip || partner?.zip || "",
            building_apt: order.delivery_building_apt || partner?.building_apt || "",
            delivery_fee: order.delivery_fee || 0,
            error_message: "",
        });
    }

    setTab(tabName) {
        this.state.activeTab = tabName;
        this.state.error_message = "";
    }

    onDeliveryFeeInput(ev) {
        const val = parseFloat(ev.target.value || 0);
        this.state.delivery_fee = isNaN(val) ? 0 : val;
    }

    async applyDeliveryFee() {
        if (this.state.delivery_fee < 0) {
            this.state.error_message = _t("Delivery fee cannot be negative.");
            return;
        }
        const order = this.props.order;
        const posConfig = this.props.pos.config;
        const feeProductId = posConfig.delivery_fee_product_id?.[0] || posConfig.delivery_fee_product_id;

        let deliveryProduct = null;
        if (feeProductId) {
            deliveryProduct = this.props.pos.db.get_product_by_id(feeProductId);
        }

        const existingLine = order.getOrderlines?.().find((line) => {
            const prod = line.getProduct?.() || line.product;
            const code = prod?.default_code || "";
            return (prod?.id || prod) === feeProductId || code === "DELIVERY_FEE" || line.is_delivery_line;
        });

        if (existingLine) {
            existingLine.set_unit_price(this.state.delivery_fee);
        } else if (deliveryProduct) {
            await order.add_product(deliveryProduct, {
                price: this.state.delivery_fee,
                quantity: 1,
                is_delivery_line: true,
            });
        } else {
            this.notification.add(
                _t("Delivery Fee set to %s. (DELIVERY_FEE line added).", this.state.delivery_fee),
                { type: "info" }
            );
        }

        this.notification.add(_t("Delivery fee applied successfully."), { type: "success" });
    }

    validateInputs() {
        this.state.error_message = "";

        if (!this.state.customer_name.trim()) {
            this.state.error_message = _t("Customer Name is required.");
            return false;
        }

        if (!this.state.mobile.trim()) {
            this.state.error_message = _t("Customer Mobile Number is required.");
            return false;
        }

        if (!this.state.scheduled_datetime) {
            this.state.error_message = _t("Scheduled Pickup / Delivery Date & Time Slot is required.");
            return false;
        }

        if (this.state.activeTab === "delivery") {
            if (!this.state.street.trim() && !this.state.city.trim()) {
                this.state.error_message = _t("Full Delivery Address (Street & City) is required for Home Delivery.");
                return false;
            }
        }

        return true;
    }

    confirm() {
        if (!this.validateInputs()) {
            return;
        }

        this.props.getPayload({
            fulfillment_type: this.state.activeTab,
            scheduled_datetime: this.state.scheduled_datetime,
            delivery_address_name: this.state.customer_name.trim(),
            delivery_address_phone: this.state.mobile.trim(),
            delivery_street: this.state.street.trim(),
            delivery_city: this.state.city.trim(),
            delivery_zip: this.state.zip.trim(),
            delivery_building_apt: this.state.building_apt.trim(),
            delivery_fee: this.state.delivery_fee,
        });

        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
