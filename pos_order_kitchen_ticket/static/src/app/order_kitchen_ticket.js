/** @odoo-module **/

import { Component } from "@odoo/owl";
import { formatDateTime } from "@web/core/l10n/dates";

export class OrderKitchenTicket extends Component {
    static template = "pos_order_kitchen_ticket.OrderKitchenTicket";
    static props = {
        order: Object,
    };

    get order() {
        return this.props.order;
    }

    get orderNumber() {
        return this.order.tracking_number || this.order.pos_reference || "";
    }

    get dateOrder() {
        return this.order.date_order ? formatDateTime(this.order.date_order) : "";
    }

    get lines() {
        return this.order.lines
            .filter((line) => !line.isTipLine() && line.qty)
            .map((line) => ({
                id: line.uuid,
                qty: line.getQuantityStr(),
                name: line.getFullProductName(),
            }));
    }
}
