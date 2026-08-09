/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

function formatToOdooDatetime(val) {
    if (!val) return false;
    let str = String(val).trim().replace("T", " ");
    if (str.length === 16) {
        str += ":00";
    }
    return str;
}

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

function setOrderPartner(order, partner) {
    if (!order || !partner) return;
    if (typeof order.setPartner === "function") {
        order.setPartner(partner);
    } else if (typeof order.set_partner === "function") {
        order.set_partner(partner);
    } else {
        order.partner = partner;
    }
}

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
        const currentPartner = getOrderPartner(order);

        let initialDatetime = order.scheduled_datetime;
        if (!initialDatetime) {
            const now = new Date();
            now.setHours(now.getHours() + 2);
            now.setMinutes(0);
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, "0");
            const day = String(now.getDate()).padStart(2, "0");
            const hours = String(now.getHours()).padStart(2, "0");
            const mins = String(now.getMinutes()).padStart(2, "0");
            initialDatetime = `${year}-${month}-${day}T${hours}:${mins}`;
        } else if (typeof initialDatetime === "string") {
            initialDatetime = initialDatetime.trim().replace(" ", "T");
            if (initialDatetime.length > 16) {
                initialDatetime = initialDatetime.slice(0, 16);
            }
        }

        this.state = useState({
            activeTab: order.fulfillment_type || "pickup",
            searchPartnerQuery: currentPartner?.name || "",
            selectedPartner: currentPartner,
            showPartnerDropdown: false,
            customer_name: order.delivery_address_name || currentPartner?.name || "",
            mobile: order.delivery_address_phone || currentPartner?.mobile || currentPartner?.phone || "",
            scheduled_datetime: initialDatetime,
            street: order.delivery_street || currentPartner?.street || "",
            city: order.delivery_city || currentPartner?.city || "",
            zip: order.delivery_zip || currentPartner?.zip || "",
            building_apt: order.delivery_building_apt || currentPartner?.building_apt || "",
            delivery_fee: order.delivery_fee || 0,
            error_message: "",
        });
    }

    get filteredPartners() {
        const query = (this.state.searchPartnerQuery || "").trim().toLowerCase();
        if (!query) {
            return [];
        }
        const db = this.props.pos?.db;
        const partners = db?.get_partners_sorted ? db.get_partners_sorted(100) : [];
        return partners.filter((p) => {
            const name = (p.name || "").toLowerCase();
            const phone = (p.phone || "").toLowerCase();
            const mobile = (p.mobile || "").toLowerCase();
            const vat = (p.vat || "").toLowerCase();
            return name.includes(query) || phone.includes(query) || mobile.includes(query) || vat.includes(query);
        }).slice(0, 10);
    }

    onSearchPartnerInput(ev) {
        this.state.searchPartnerQuery = ev.target.value;
        this.state.customer_name = ev.target.value;
        this.state.showPartnerDropdown = true;
    }

    async onClickOpenPartnerPicker() {
        try {
            const order = this.props.order;
            if (typeof this.props.pos?.selectPartner === "function") {
                await this.props.pos.selectPartner(order);
            }
            const partner = getOrderPartner(order);
            if (partner) {
                this.selectPartner(partner);
            }
        } catch (e) {
            console.error("Error opening partner picker:", e);
        }
    }

    selectPartner(partner) {
        this.state.selectedPartner = partner;
        this.state.customer_name = partner.name || "";
        this.state.mobile = partner.mobile || partner.phone || "";
        this.state.street = partner.street || "";
        this.state.city = partner.city || "";
        this.state.zip = partner.zip || "";
        this.state.building_apt = partner.building_apt || "";
        this.state.searchPartnerQuery = partner.name || "";
        this.state.showPartnerDropdown = false;

        setOrderPartner(this.props.order, partner);
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

        const partner = this.state.selectedPartner || getOrderPartner(this.props.order);
        if (partner) {
            setOrderPartner(this.props.order, partner);
        }

        const formattedOdooDatetime = formatToOdooDatetime(this.state.scheduled_datetime);

        this.props.getPayload({
            fulfillment_type: this.state.activeTab,
            scheduled_datetime: formattedOdooDatetime,
            delivery_address_id: partner ? partner.id : false,
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
