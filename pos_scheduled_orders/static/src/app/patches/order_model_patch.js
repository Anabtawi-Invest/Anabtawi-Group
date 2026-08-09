/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        this.fulfillment_type = vals?.fulfillment_type || this.fulfillment_type || null;
        this.scheduled_datetime = vals?.scheduled_datetime || this.scheduled_datetime || "";
        this.is_advance_deposit = vals?.is_advance_deposit !== undefined ? vals.is_advance_deposit : false;
        this.jofotara_status = vals?.jofotara_status || this.jofotara_status || "pending";
        this.delivery_address_id = vals?.delivery_address_id || this.delivery_address_id || null;
        this.delivery_address_name = vals?.delivery_address_name || this.delivery_address_name || "";
        this.delivery_address_phone = vals?.delivery_address_phone || this.delivery_address_phone || "";
        this.delivery_street = vals?.delivery_street || this.delivery_street || "";
        this.delivery_city = vals?.delivery_city || this.delivery_city || "";
        this.delivery_building_apt = vals?.delivery_building_apt || this.delivery_building_apt || "";
        this.delivery_zip = vals?.delivery_zip || this.delivery_zip || "";
        this.is_catering = vals?.is_catering || this.is_catering || false;
        this.delivery_fee = vals?.delivery_fee || this.delivery_fee || 0;
        this.catering_fee = vals?.catering_fee || this.catering_fee || 0;
    },

    getFulfillmentData() {
        return {
            fulfillment_type: this.fulfillment_type,
            scheduled_datetime: this.scheduled_datetime,
            is_advance_deposit: this.is_advance_deposit,
            jofotara_status: this.jofotara_status,
            delivery_address_id: this.delivery_address_id,
            delivery_address_name: this.delivery_address_name,
            delivery_address_phone: this.delivery_address_phone,
            delivery_street: this.delivery_street,
            delivery_city: this.delivery_city,
            delivery_building_apt: this.delivery_building_apt,
            delivery_zip: this.delivery_zip,
            is_catering: this.is_catering,
            delivery_fee: this.delivery_fee,
            catering_fee: this.catering_fee,
        };
    },

    setFulfillmentData(data) {
        this.update({
            fulfillment_type: data.fulfillment_type || null,
            scheduled_datetime: data.scheduled_datetime || "",
            is_advance_deposit: data.is_advance_deposit !== undefined ? data.is_advance_deposit : this.is_advance_deposit,
            jofotara_status: data.jofotara_status || this.jofotara_status,
            delivery_address_id: data.delivery_address_id || null,
            delivery_address_name: data.delivery_address_name || "",
            delivery_address_phone: data.delivery_address_phone || "",
            delivery_street: data.delivery_street || "",
            delivery_city: data.delivery_city || "",
            delivery_building_apt: data.delivery_building_apt || "",
            delivery_zip: data.delivery_zip || "",
            is_catering: data.is_catering !== undefined ? data.is_catering : this.is_catering,
            delivery_fee: data.delivery_fee !== undefined ? data.delivery_fee : this.delivery_fee,
            catering_fee: data.catering_fee !== undefined ? data.catering_fee : this.catering_fee,
        });
        this.trigger?.("change", this);
    },

    export_as_JSON() {
        const json = super.export_as_JSON ? super.export_as_JSON() : {};
        json.fulfillment_type = this.fulfillment_type || false;
        json.scheduled_datetime = this.scheduled_datetime || false;
        json.is_advance_deposit = this.is_advance_deposit || false;
        json.jofotara_status = this.jofotara_status || "pending";
        json.delivery_address_id = this.delivery_address_id || false;
        json.delivery_address_name = this.delivery_address_name || false;
        json.delivery_address_phone = this.delivery_address_phone || false;
        json.delivery_street = this.delivery_street || false;
        json.delivery_city = this.delivery_city || false;
        json.delivery_building_apt = this.delivery_building_apt || false;
        json.delivery_zip = this.delivery_zip || false;
        json.is_catering = this.is_catering || false;
        json.delivery_fee = this.delivery_fee || 0;
        json.catering_fee = this.catering_fee || 0;
        return json;
    },

    init_from_JSON(json) {
        if (super.init_from_JSON) {
            super.init_from_JSON(json);
        }
        this.fulfillment_type = json.fulfillment_type || null;
        this.scheduled_datetime = json.scheduled_datetime || "";
        this.is_advance_deposit = json.is_advance_deposit || false;
        this.jofotara_status = json.jofotara_status || "pending";
        this.delivery_address_id = json.delivery_address_id || null;
        this.delivery_address_name = json.delivery_address_name || "";
        this.delivery_address_phone = json.delivery_address_phone || "";
        this.delivery_street = json.delivery_street || "";
        this.delivery_city = json.delivery_city || "";
        this.delivery_building_apt = json.delivery_building_apt || "";
        this.delivery_zip = json.delivery_zip || "";
        this.is_catering = json.is_catering || false;
        this.delivery_fee = json.delivery_fee || 0;
        this.catering_fee = json.catering_fee || 0;
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        data.fulfillment_type = this.fulfillment_type || false;
        data.scheduled_datetime = this.scheduled_datetime || false;
        data.is_advance_deposit = this.is_advance_deposit || false;
        data.jofotara_status = this.jofotara_status || "pending";
        data.delivery_address_id = this.delivery_address_id || false;
        data.delivery_address_name = this.delivery_address_name || false;
        data.delivery_address_phone = this.delivery_address_phone || false;
        data.delivery_street = this.delivery_street || false;
        data.delivery_city = this.delivery_city || false;
        data.delivery_building_apt = this.delivery_building_apt || false;
        data.delivery_zip = this.delivery_zip || false;
        data.is_catering = this.is_catering || false;
        data.delivery_fee = this.delivery_fee || 0;
        data.catering_fee = this.catering_fee || 0;
        return data;
    },
});
