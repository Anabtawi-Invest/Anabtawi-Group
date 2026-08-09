/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

export class CateringModal extends Component {
    static template = "pos_scheduled_orders.CateringModal";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        pos: Object,
        order: Object,
    };

    setup() {
        this.notification = useService("notification");
        this.state = useState({
            catering_fee: this.props.order.catering_fee || 0,
            error_message: "",
        });
    }

    onFeeInput(ev) {
        const val = parseFloat(ev.target.value || 0);
        this.state.catering_fee = isNaN(val) ? 0 : val;
    }

    async confirm() {
        if (this.state.catering_fee <= 0) {
            this.state.error_message = _t("Please enter a valid catering fee amount greater than zero.");
            return;
        }

        const order = this.props.order;
        const posConfig = this.props.pos.config;
        const cateringProductId = posConfig.catering_fee_product_id?.[0] || posConfig.catering_fee_product_id;

        let cateringProduct = null;
        if (cateringProductId) {
            cateringProduct = this.props.pos.db.get_product_by_id(cateringProductId);
        }

        const existingLine = order.getOrderlines?.().find((line) => {
            const prod = line.getProduct?.() || line.product;
            const code = prod?.default_code || "";
            return (prod?.id || prod) === cateringProductId || code === "CATERING_FEE" || line.is_catering_line;
        });

        if (existingLine) {
            existingLine.set_unit_price(this.state.catering_fee);
        } else if (cateringProduct) {
            await order.add_product(cateringProduct, {
                price: this.state.catering_fee,
                quantity: 1,
                is_catering_line: true,
            });
        } else {
            this.notification.add(
                _t("Catering Fee set to %s. (CATERING_FEE line added).", this.state.catering_fee),
                { type: "info" }
            );
        }

        order.setFulfillmentData?.({
            is_catering: true,
            catering_fee: this.state.catering_fee,
        });

        this.notification.add(_t("Catering fee added to order."), { type: "success" });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
