/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosTicketPrinterService } from "@point_of_sale/app/services/pos_ticket_printer_service";

patch(PosTicketPrinterService.prototype, {
    async printOrderReceipt({ order, printBillActionTriggered = false } = {}) {
        // Read before printing: the receipt print increments nb_print.
        const isFirstPrintAfterPayment =
            Boolean(this.config.print_order_kitchen_ticket) &&
            !printBillActionTriggered &&
            Boolean(order?.finalized) &&
            !order.isRefund &&
            !order.nb_print;

        const result = await super.printOrderReceipt(...arguments);

        if (isFirstPrintAfterPayment && result?.successful) {
            await this.printOrderKitchenTicket(order);
        }
        return result;
    },

    getOrderKitchenTicketData(order) {
        const lines = order.lines
            .filter((line) => !line.isTipLine() && !line.isServiceFeeLine() && line.qty)
            .map((line) => ({
                qty: line.getQuantityStr(),
                name: line.getFullProductName(),
            }));
        return {
            config_name: this.config.name,
            order_number: order.tracking_number || order.pos_reference,
            pos_reference: order.tracking_number ? order.pos_reference : "",
            date: order.formatDateOrTime("date_order", "datetime"),
            lines,
        };
    },

    async printOrderKitchenTicket(order) {
        const data = this.getOrderKitchenTicketData(order);
        if (!data.lines.length) {
            return;
        }
        const iframe = await this.generateIframe(
            "pos_order_kitchen_ticket.pos_order_kitchen_ticket",
            data
        );
        return await this.printWithFallback({ iframe, webFallback: false });
    },
});
