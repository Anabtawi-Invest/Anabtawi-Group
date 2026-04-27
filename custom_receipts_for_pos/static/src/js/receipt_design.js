/** @odoo-module */

import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";
import { Component, xml } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(OrderReceipt.prototype, {
    setup() {
        super.setup(...arguments);
        this.pos = useService("pos");
    },

    get isCustomReceipt() {
        return Boolean(
            this.pos &&
            this.pos.config &&
            this.pos.config.is_custom_receipt &&
            this.pos.config.design_receipt
        );
    },

    get customReceiptProps() {
        const order = this.props.order;

        return {
            order: order,
            pos: this.pos,
            paymentLines: this.paymentLines || [],
            header: this.header || {},
            formatCurrency: this.formatCurrency.bind(this),
            vatText: this.vatText,
        };
    },

    get customReceiptComponent() {
        const design = this.pos.config.design_receipt || "<div class='pos-receipt p-2'></div>";

        return class CustomPosReceipt extends Component {
            static template = xml`${design}`;
            static props = {
                order: { type: Object, optional: true },
                pos: { type: Object, optional: true },
                paymentLines: { type: Array, optional: true },
                header: { type: Object, optional: true },
                formatCurrency: { type: Function, optional: true },
                vatText: { type: String, optional: true },
            };
        };
    },
});
