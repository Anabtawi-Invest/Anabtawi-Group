/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";

patch(ReceiptScreen.prototype, {
    async printReceipt() {
        const order = this.currentOrder;
        const hasDeposit = order.get_orderlines().some((l) => l.is_pledge_line || l.is_advance_deposit_line);

        if (!hasDeposit) {
            return await super.printReceipt(...arguments);
        }

        order.__print_mode = "products";
        await super.printReceipt(...arguments);

        order.__print_mode = "deposit";
        await super.printReceipt(...arguments);

        order.__print_mode = null;
    },
});
