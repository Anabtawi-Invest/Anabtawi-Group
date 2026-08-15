/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";

patch(OrderSummary.prototype, {
    async updateSelectedOrderline({ buffer, key }) {
        const order = this.pos.getOrder();
        const selectedLine = order?.getSelectedOrderline?.();
        if (
            selectedLine &&
            this.pos.numpadMode === "quantity" &&
            this.pos.isPosQtyChangeRestricted(selectedLine, order)
        ) {
            if (buffer === null || (key === "Backspace" && !this.numberBuffer.state.buffer)) {
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
            val !== "remove" &&
            this.pos.isPosQtyChangeRestricted(selectedLine, order)
        ) {
            this.numberBuffer.reset();
            this.pos.showPosQtyChangeDenied();
            return;
        }
        return super._setValue(val);
    },
});
