/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/store/models";

patch(Order.prototype, {
    add_product(product, options) {
        const res = super.add_product(product, options);

        try {
            if (product && product.requires_pledge && product.pledge_product_id && product.pledge_amount > 0) {
                const pledgeProductId = product.pledge_product_id[0] || product.pledge_product_id;
                const pledgeProduct = this.pos.db.get_product_by_id(pledgeProductId);

                if (pledgeProduct) {
                    const mainLine = this.get_last_orderline();
                    const qty = mainLine ? mainLine.get_quantity() : 1;

                    super.add_product(pledgeProduct, { price: product.pledge_amount });

                    const pledgeLine = this.get_last_orderline();
                    pledgeLine.is_pledge_line = true;
                    pledgeLine.pledge_origin_product_id = product.id;

                    pledgeLine.set_unit_price(product.pledge_amount);
                    pledgeLine.set_quantity(qty);
                }
            }
        } catch (e) {
            console.warn("Pledge auto-add failed:", e);
        }

        return res;
    },
});
