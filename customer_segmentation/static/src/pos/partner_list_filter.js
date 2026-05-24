import { patch } from "@web/core/utils/patch";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

patch(PartnerList.prototype, {
    getPartners(partners) {
        if (!this.pos.customerSegmentationPosTeam) {
            return super.getPartners(partners || []);
        }
        const posCustomersOnly = (partners || []).filter(
            (partner) => partner && partner.is_pos_customer === true
        );
        return super.getPartners(posCustomersOnly);
    },
});
