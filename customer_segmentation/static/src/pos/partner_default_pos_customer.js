import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    editPartnerContext() {
        return {
            ...super.editPartnerContext(...arguments),
            default_is_pos_customer: true,
        };
    },
});
