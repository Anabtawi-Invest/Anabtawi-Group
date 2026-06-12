/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

PosOrder.extraFields = {
    ...(PosOrder.extraFields || {}),
    customer_latitude: { type: "float" },
    customer_longitude: { type: "float" },
    customer_location_captured: { type: "boolean" },
    customer_payment_preference: { type: "string" },
};

patch(PosOrder.prototype, {
    ensureSelfOrderLineChanges() {
        if (!this.uiState) {
            this.uiState = {};
        }
        if (!this.uiState.lineChanges) {
            this.uiState.lineChanges = {};
        }
    },

    initState() {
        super.initState(...arguments);
        this.ensureSelfOrderLineChanges();
    },

    restoreState(uiState) {
        super.restoreState(...arguments);
        this.ensureSelfOrderLineChanges();
    },

    get changes() {
        this.ensureSelfOrderLineChanges();
        return super.changes;
    },

    get unsentLines() {
        this.ensureSelfOrderLineChanges();
        return super.unsentLines;
    },

    recomputeChanges() {
        this.ensureSelfOrderLineChanges();
        super.recomputeChanges(...arguments);
    },
});
