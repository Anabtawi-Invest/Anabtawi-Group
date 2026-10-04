/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { OrderKitchenTicket } from "./order_kitchen_ticket";

patch(PosStore.prototype, {
    async printReceipt({
        order = this.getOrder(),
        printBillActionTriggered = false,
    } = {}) {
        // Read before printing: the receipt print increments nb_print.
        const isFirstPrintAfterPayment =
            Boolean(this.config.print_order_kitchen_ticket) &&
            !printBillActionTriggered &&
            Boolean(order?.finalized) &&
            !order.isRefund &&
            !order.nb_print;

        const result = await super.printReceipt(...arguments);

        // `successful` is only set when a real printer printed (not the browser dialog).
        if (isFirstPrintAfterPayment && result?.successful) {
            await this.printOrderKitchenTicket(order);
        }
        return result;
    },

    async printOrderKitchenTicket(order) {
        const hasLines = order.lines.some((line) => !line.isTipLine() && line.qty);
        if (!hasLines) {
            return;
        }
        return await this.printer.print(OrderKitchenTicket, { order }, this.printOptions);
    },
});
