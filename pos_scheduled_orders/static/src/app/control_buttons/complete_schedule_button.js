/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { CompleteScheduleModal } from "../complete_schedule_modal/complete_schedule_modal";

patch(ControlButtons.prototype, {
    async onClickCompleteSchedule() {
        this.dialog.add(CompleteScheduleModal, {
            pos: this.pos,
        });
    },
});
