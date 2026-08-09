/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { FulfillmentModal } from "../fulfillment_modal/fulfillment_modal";

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },

    get fulfillmentButtonLabel() {
        const order = this.pos.getOrder?.();
        if (order?.fulfillment_type === "delivery") {
            return _t("توصيل منزلي - Home Delivery");
        } else if (order?.fulfillment_type === "pickup") {
            return _t("استلام من الفرع - Store Pickup");
        }
        return _t("طلبيات تواصي / Scheduled Orders");
    },

    fulfillmentButtonClass() {
        const order = this.pos.getOrder?.();
        if (order?.fulfillment_type === "delivery") {
            return "btn btn-danger btn-lg lh-lg text-white fw-bold";
        } else if (order?.fulfillment_type === "pickup") {
            return "btn btn-primary btn-lg lh-lg text-white fw-bold";
        }
        return "btn btn-secondary btn-lg lh-lg";
    },

    async onClickFulfillment() {
        const order = this.pos.getOrder?.();
        if (!order) {
            return;
        }

        const payload = await makeAwaitable(this.dialog, FulfillmentModal, {
            pos: this.pos,
            order: order,
        });

        if (payload) {
            order.setFulfillmentData?.(payload);
        }
    },
});
