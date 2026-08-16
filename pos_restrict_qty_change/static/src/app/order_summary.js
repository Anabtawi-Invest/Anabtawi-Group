/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";

function isRemoveOrZeroQty(val) {
    if (val === "remove" || val === null) {
        return true;
    }
    if (val === "" || val === undefined) {
        return true;
    }
    const qty = typeof val === "number" ? val : parseFloat(val);
    return !isNaN(qty) && qty === 0;
}

patch(OrderSummary.prototype, {
    async updateSelectedOrderline({ buffer, key }) {
        const order = this.pos.getOrder();
        const selectedLine = order?.getSelectedOrderline?.();
        if (
            selectedLine &&
            this.pos.numpadMode === "quantity" &&
            this.pos.isPosQtyChangeRestricted(selectedLine, order)
        ) {
            // Allow deleting a wrongly added line (Backspace / clear / qty 0).
            if (key === "Backspace" || isRemoveOrZeroQty(buffer)) {
                return super.updateSelectedOrderline({ buffer, key });
            }
            this.numberBuffer.reset();
            this.pos.showPosQtyChangeDenied();
            return;
        }
        return super.updateSelectedOrderline({ buffer, key });
    },

    _setValue(val) {
        const order = this.currentOrder;
        const selectedLine = order?.getSelectedOrderline?.();
        if (
            selectedLine &&
            this.pos.numpadMode === "quantity" &&
            this.pos.isPosQtyChangeRestricted(selectedLine, order) &&
            !isRemoveOrZeroQty(val)
        ) {
            this.numberBuffer.reset();
            this.pos.showPosQtyChangeDenied();
            return;
        }
        return super._setValue(val);
    },
});
