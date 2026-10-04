/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { OrderKitchenTicket, kitchenTicketWebPrint } from "./order_kitchen_ticket";

OrderReceipt.components = { ...OrderReceipt.components, OrderKitchenTicket };

patch(OrderReceipt.prototype, {
    setup() {
        super.setup(...arguments);
        this.withOrderKitchenTicket =
            Boolean(this.props.order?.uuid) &&
            kitchenTicketWebPrint.orderUuid === this.props.order.uuid;
    },
});
