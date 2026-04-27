/** @odoo-module */

import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";
import { Component, xml } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Odoo 19: OrderReceipt props changed to { order, basic_receipt }.
 * This patch lets you render a custom QWeb/OWL template saved in
 * pos.config.design_receipt (Text field).
 */
patch(OrderReceipt.prototype, {
    setup() {
        super.setup(...arguments);
        this.pos = useService("pos");
    },

    // Keep the original name used in your XML (isTrue)
    get isTrue() {
        return Boolean(this.pos?.config?.is_custom_receipt && this.pos?.config?.design_receipt);
    },

    get templateProps() {
        const order = this.props.order;

        // Some custom templates (from v18) expect a `receipt` structure.
        // In v19, `export_for_printing` may or may not exist depending on the POS build.
        const exportedReceipt = order?.export_for_printing ? order.export_for_printing() : {};

        return {
            order,
            receipt: exportedReceipt,
            paymentLines: this.paymentLines || [],
            pos: this.pos,
        };
    },

    get templateComponent() {
        const design = this.pos?.config?.design_receipt || "<div class='pos-receipt p-2'/>";

        return class CustomReceipt extends Component {
            static template = xml`${design}`;
            static props = {
                order: { type: Object, optional: true },
                receipt: { type: Object, optional: true },
                paymentLines: { type: Array, optional: true },
                pos: { type: Object, optional: true },
            };
        };
    },
});
