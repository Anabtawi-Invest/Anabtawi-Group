/** @odoo-module **/

import { Component } from "@odoo/owl";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { useService } from "@web/core/utils/hooks";
import { CompleteScheduleModal } from "@pos_scheduled_orders/app/complete_schedule_modal/complete_schedule_modal";

export class CompleteScheduleButton extends Component {
    static template = "pos_scheduled_orders.CompleteScheduleButton";

    setup() {
        this.dialog = useService("dialog");
        this.pos = useService("pos");
    }

    async onClick() {
        this.dialog.add(CompleteScheduleModal, {
            pos: this.pos,
        });
    }
}

ProductScreen.addControlButton({
    component: CompleteScheduleButton,
    condition: function () {
        return this.pos?.config?.enable_fulfillment_schedule;
    },
});
