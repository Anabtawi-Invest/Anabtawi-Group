/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { CateringModal } from "../catering_modal/catering_modal";

patch(ControlButtons.prototype, {
    cateringButtonClass() {
        const order = this.pos.getOrder?.();
        if (order?.is_catering) {
            return "btn btn-success btn-lg lh-lg text-white fw-bold";
        }
        return "btn btn-outline-success btn-lg lh-lg";
    },

    get cateringButtonLabel() {
        const order = this.pos.getOrder?.();
        if (order?.is_catering) {
            return _t("تم إدراج رسوم الضيافة");
        }
        return _t("إضافة خدمة ضيافة - Catering");
    },

    async onClickCatering() {
        const order = this.pos.getOrder?.();
        if (!order) {
            return;
        }

        await makeAwaitable(this.dialog, CateringModal, {
            pos: this.pos,
            order: order,
        });
    },
});
