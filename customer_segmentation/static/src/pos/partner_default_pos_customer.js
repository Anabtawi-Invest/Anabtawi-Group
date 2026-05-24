import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { user } from "@web/core/user";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.customerSegmentationPosTeam = await user.hasGroup(
            "customer_segmentation.group_pos_team"
        );
    },

    editPartnerContext() {
        return {
            ...super.editPartnerContext(...arguments),
            default_is_pos_customer: true,
        };
    },
});
