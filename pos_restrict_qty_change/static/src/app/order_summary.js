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

function isDeleteKey(key) {
    return key === "Backspace" || key === "Delete";
}

patch(OrderSummary.prototype, {
    _removeRestrictedOrderline(selectedLine) {
        this.numberBuffer.reset();
        const line = selectedLine.combo_parent_id || selectedLine;
        this.currentOrder.removeOrderline(line);
        this.pos.numpadMode = "quantity";
    },

    async updateSelectedOrderline({ buffer, key }) {
        const order = this.pos.getOrder();
        const selectedLine = order?.getSelectedOrderline?.();
        if (
            selectedLine &&
            this.pos.numpadMode === "quantity" &&
            this.pos.isPosQtyChangeRestricted(selectedLine, order)
        ) {
            // Always allow deleting a wrongly added line.
            if (isDeleteKey(key) || isRemoveOrZeroQty(buffer)) {
                this._removeRestrictedOrderline(selectedLine);
                return;
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
            this.pos.isPosQtyChangeRestricted(selectedLine, order)
        ) {
            if (isRemoveOrZeroQty(val)) {
                this._removeRestrictedOrderline(selectedLine);
                return;
            }
            this.numberBuffer.reset();
            this.pos.showPosQtyChangeDenied();
            return;
        }
        return super._setValue(val);
    },
});
