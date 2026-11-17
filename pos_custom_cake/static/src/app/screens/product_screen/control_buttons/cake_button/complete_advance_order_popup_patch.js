/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { CompleteAdvanceOrderPopup } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/complete_advance_order_popup";

patch(CompleteAdvanceOrderPopup.prototype, {
    async _loadAdvanceOrders() {
        await super._loadAdvanceOrders(...arguments);
        const orders = this.state.advance_orders || [];
        if (!orders.length) {
            return;
        }
        try {
            const linked = await this.orm.searchRead(
                "pos.advance.order",
                [
                    ["id", "in", orders.map((o) => o.id)],
                    ["cake_order_id", "!=", false],
                ],
                ["id"]
            );
            if (!linked?.length) {
                return;
            }
            const exclude = new Set(linked.map((row) => row.id));
            this.state.advance_orders = orders.filter((order) => !exclude.has(order.id));
        } catch (_error) {
            // Field may be missing before module upgrade; keep the original list.
        }
    },
});
