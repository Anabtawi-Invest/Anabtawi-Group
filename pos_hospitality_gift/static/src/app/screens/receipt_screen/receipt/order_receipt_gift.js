/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";

patch(OrderReceipt.prototype, {
    get giftLines() {
        return this.order.lines?.filter((line) => line.is_gift) || [];
    },

    get hasGiftLines() {
        return this.giftLines.length > 0;
    },
});
