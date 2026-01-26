/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";

export class DiscountPopup extends Component {
    static template = "pos_advance_orders.DiscountPopup";

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");

        const profile = this.pos.config.discount_profile_id; // may be [id, name] or false
        const maxFixed = (this.pos.config.max_fixed_total_discount || 0.99);

        // buttons loaded via config extra (we'll inject below in loader patch)
        const buttons = this.pos.config.discount_buttons || [];

        this.state = useState({
            buttons,
            fixed: "",
            maxFixed,
        });
    }

    cancel() {
        this.popup.close();
    }

    _getDiscountProduct() {
        const dp = this.pos.config.discount_product_id;
        const id = dp && (dp[0] || dp);
        if (!id) throw new Error("Missing discount_product_id in POS config");
        const prod = this.pos.db.get_product_by_id(id);
        if (!prod) throw new Error("Discount product not loaded in POS");
        return prod;
    }

    _upsertDiscountLine(amount) {
        const order = this.pos.get_order();
        const discountProduct = this._getDiscountProduct();

        // find existing discount line
        const existing = order.get_orderlines().find((l) => l.is_total_discount_line);
        if (existing) {
            existing.set_unit_price(-Math.abs(amount));
            existing.set_quantity(1);
            return;
        }

        order.add_product(discountProduct, { price: -Math.abs(amount) });
        const line = order.get_last_orderline();
        line.is_total_discount_line = true;
        line.set_unit_price(-Math.abs(amount));
        line.set_quantity(1);
    }

    applyPercent(percent) {
        const order = this.pos.get_order();
        const total = order.get_total_with_tax();
        const amount = (total * percent) / 100.0;
        this._upsertDiscountLine(amount);
        this.popup.close();
    }

    applyFixed() {
        const val = parseFloat(this.state.fixed || "0") || 0;

        // must be decimal less than 1.0
        if (!(val > 0 && val < 1.0)) {
            alert("Fixed discount must be > 0 and < 1.0 (e.g. 0.9).");
            return;
        }

        if (val > this.state.maxFixed) {
            alert(`Fixed discount cannot exceed ${this.state.maxFixed}.`);
            return;
        }

        this._upsertDiscountLine(val);
        this.popup.close();
    }
}
