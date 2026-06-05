/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";

PosOrder.extraFields = {
    ...(PosOrder.extraFields || {}),
    customer_latitude: { type: "float" },
    customer_longitude: { type: "float" },
    customer_location_captured: { type: "boolean" },
};
