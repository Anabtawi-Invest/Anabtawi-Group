/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";

export class AdvanceOrdersPopup extends Component {
    static template = "pos_advance_orders.AdvanceOrdersPopup";

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");
        this.popup = useService("popup");

        const order = this.pos.get_order();
        const partner = order.get_partner();

        this.state = useState({
            mobile: partner ? (partner.mobile || partner.phone || "") : "",
            dueDate: "",
            note: "",
            depositAmount: "",
        });
    }

    cancel() {
        this.popup.close();
    }

    async confirm() {
        const order = this.pos.get_order();
        const orderlines = order.get_orderlines();

        const lines = orderlines.filter((l) => !l.is_pledge_line && !l.is_advance_deposit_line);
        if (!lines.length) {
            this.popup.close();
            return;
        }

        let partner = order.get_partner();
        if (!partner && this.state.mobile) {
            const candidates = this.pos.db.search_partner(this.state.mobile) || [];
            partner = candidates.length ? candidates[0] : null;
        }

        const ao_vals = {
            pos_config_id: this.pos.config.id,
            partner_id: partner ? partner.id : false,
            partner_mobile: this.state.mobile || (partner ? (partner.mobile || partner.phone) : false),
            due_date: this.state.dueDate || false,
            note: this.state.note || "",
            line_ids: lines.map((l) => [0, 0, {
                product_id: l.product.id,
                qty: l.get_quantity(),
                price_unit: l.get_unit_price(),
                name: l.product.display_name,
            }]),
        };

        const ao_id = await this.orm.create("pos.advance.order", [ao_vals]);

        const depositAmount = parseFloat(this.state.depositAmount || "0") || 0;
        if (depositAmount > 0) {
            const depositProductId =
                (this.pos.config.advance_deposit_product_id && this.pos.config.advance_deposit_product_id[0]) ||
                this.pos.config.advance_deposit_product_id;

            if (!depositProductId) {
                throw new Error("Missing advance_deposit_product_id in POS config");
            }

            const depositProduct = this.pos.db.get_product_by_id(depositProductId);
            if (!depositProduct) {
                throw new Error("Deposit product not loaded in POS");
            }

            // clear cart
            orderlines.slice().forEach((l) => order.removeOrderline(l));

            if (partner) order.set_partner(partner);

            order.advance_order_id = ao_id;
            order.customer_mobile = ao_vals.partner_mobile;

            order.add_product(depositProduct, { price: depositAmount });
            const depLine = order.get_last_orderline();
            depLine.is_advance_deposit_line = true;
            depLine.set_unit_price(depositAmount);
            depLine.set_quantity(1);

            this.pos.showScreen("PaymentScreen");
        } else {
            // no deposit: clear cart after saving
            orderlines.slice().forEach((l) => order.removeOrderline(l));
        }

        this.popup.close();
    }
}
