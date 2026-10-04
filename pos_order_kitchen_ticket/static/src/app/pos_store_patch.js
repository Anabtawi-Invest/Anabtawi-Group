/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { OrderKitchenTicket, kitchenTicketWebPrint } from "./order_kitchen_ticket";

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
            !order.nb_print &&
            this.hasOrderKitchenTicketLines(order);

        // Without a receipt printer the browser prints a single document, so the
        // ticket is added to it on a new page instead of being a second job.
        const useWebPrint = isFirstPrintAfterPayment && !this.hardwareProxy?.printer;
        if (useWebPrint) {
            kitchenTicketWebPrint.orderUuid = order.uuid;
        }
        let result;
        try {
            result = await super.printReceipt(...arguments);
        } finally {
            kitchenTicketWebPrint.orderUuid = null;
        }

        if (isFirstPrintAfterPayment && !useWebPrint && result?.successful) {
            await this.printOrderKitchenTicket(order);
        }
        return result;
    },

    hasOrderKitchenTicketLines(order) {
        return order.lines.some((line) => !line.isTipLine() && line.qty);
    },

    async printOrderKitchenTicket(order) {
        return await this.printer.print(OrderKitchenTicket, { order }, this.printOptions);
    },
});
