/** @odoo-module */

import { registry } from "@web/core/registry";
import { Base } from "@point_of_sale/app/models/related_models";

const { DateTime } = luxon;

export class OnlineCampaignAggregator extends Base {
    static pythonModel = "online.campaign.aggregator";
}

export class OnlineDiscountCampaign extends Base {
    static pythonModel = "online.discount.campaign";

    isActiveAt(moment = DateTime.now()) {
        return (
            this.active && this.state === "approved" && this.start_datetime && this.end_datetime &&
            this.start_datetime <= moment && moment <= this.end_datetime
        );
    }

    appliesToPricelist(pricelist) {
        return Boolean(pricelist) && this.pricelist_ids.some((item) => item.id === pricelist.id);
    }

    appliesTo(product) {
        if (this.apply_scope === "all_products") {
            return true;
        }
        if (this.apply_scope === "specific_products") {
            return this.product_ids.some((candidate) => candidate.id === product.id);
        }
        const categoryIds = new Set(this.category_ids.map((category) => category.id));
        let category = product.product_tmpl_id.categ_id;
        while (category) {
            if (categoryIds.has(category.id)) {
                return true;
            }
            category = category.parent_id;
        }
        return false;
    }
}

registry.category("pos_available_models").add(
    OnlineCampaignAggregator.pythonModel, OnlineCampaignAggregator
);
registry.category("pos_available_models").add(
    OnlineDiscountCampaign.pythonModel, OnlineDiscountCampaign
);

