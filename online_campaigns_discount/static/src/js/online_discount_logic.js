/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

const { DateTime } = luxon;

function activePricelistCampaigns(campaigns, order, moment) {
    return campaigns
        .filter(
            (campaign) =>
                campaign.isActiveAt(moment) &&
                campaign.appliesToPricelist(order.pricelist_id)
        )
        .sort((left, right) => left.priority - right.priority || left.id - right.id);
}

function campaignCandidates(campaigns, order, product, moment) {
    const applicable = activePricelistCampaigns(campaigns, order, moment).filter((campaign) =>
        campaign.appliesTo(product)
    );
    if (!applicable.length) {
        return [];
    }
    const primary = applicable[0];
    return primary.allow_stacking
        ? [
              primary,
              ...applicable.slice(1).filter(
                  (campaign) =>
                      campaign.allow_stacking && campaign.aggregator_id.id === primary.aggregator_id.id
              ),
          ]
        : [primary];
}

function uncappedDiscount(campaign, gross, quantity) {
    const absoluteGross = Math.abs(gross);
    const absoluteQuantity = Math.abs(quantity);
    const percentageAmount = (absoluteGross * campaign.discount_percent) / 100;
    const cap = campaign.discount_cap_amount || 0;
    if (!cap || campaign.cap_application === "per_order") {
        return percentageAmount;
    }
    if (campaign.cap_application === "per_unit") {
        const unitGross = absoluteQuantity ? absoluteGross / absoluteQuantity : 0;
        return Math.min((unitGross * campaign.discount_percent) / 100, cap) * absoluteQuantity;
    }
    return Math.min(percentageAmount, cap);
}

function buildPerOrderAllocations(order, campaigns, moment, round) {
    const allocations = new Map();
    const remainingByCampaign = new Map();
    for (const line of order.lines) {
        const gross = line.price_unit * line.qty;
        if (!gross || !line.product_id) {
            continue;
        }
        for (const campaign of campaignCandidates(campaigns, order, line.product_id, moment)) {
            if (campaign.cap_application !== "per_order") {
                continue;
            }
            if (!remainingByCampaign.has(campaign.id)) {
                remainingByCampaign.set(
                    campaign.id,
                    campaign.discount_cap_amount ? Math.abs(campaign.discount_cap_amount) : Infinity
                );
            }
            const remaining = remainingByCampaign.get(campaign.id);
            const amount = Math.min(uncappedDiscount(campaign, gross, line.qty), remaining);
            allocations.set(`${line.uuid}:${campaign.id}`, round(amount));
            remainingByCampaign.set(campaign.id, Math.max(0, remaining - amount));
        }
    }
    return allocations;
}

const emptyCampaignValues = {
    online_campaign_id: false,
    online_aggregator_id: false,
    online_discount_percent: 0,
    online_discount_amount: 0,
    aggregator_contribution_amount: 0,
    company_contribution_amount: 0,
    online_discount_cap_amount: 0,
    cap_application: false,
    aggregator_commission_percent: 0,
    aggregator_commission_amount: 0,
    online_campaign_breakdown: false,
};

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this._onlineCampaignRecomputing = false;
        const recomputeLineOrder = ({ id }) => {
            if (this._onlineCampaignRecomputing) {
                return;
            }
            const line = this.models["pos.order.line"].get(id);
            if (line?.order_id?.state === "draft") {
                this.recomputeOnlineCampaigns(line.order_id);
            }
        };
        this.models["pos.order.line"].addEventListener("create", recomputeLineOrder);
        this.models["pos.order.line"].addEventListener("update", recomputeLineOrder);
        this.models["pos.order"].addEventListener("update", ({ id, fields }) => {
            if (
                !this._onlineCampaignRecomputing &&
                fields?.some((field) => ["lines", "pricelist_id"].includes(field))
            ) {
                this.recomputeOnlineCampaigns(this.models["pos.order"].get(id));
            }
        });
        for (const order of this.models["pos.order"].filter((candidate) => candidate.state === "draft")) {
            this.recomputeOnlineCampaigns(order);
        }
    },

    recomputeOnlineCampaigns(order = this.getOrder()) {
        if (!order || order.state !== "draft" || this._onlineCampaignRecomputing) {
            return;
        }
        const campaigns = this.models["online.discount.campaign"]?.getAll() || [];
        const moment = DateTime.now();
        const round = (amount) => order.currency.round(amount);
        const perOrderAllocations = buildPerOrderAllocations(order, campaigns, moment, round);
        this._onlineCampaignRecomputing = true;
        try {
            for (const line of order.lines) {
                const gross = line.price_unit * line.qty;
                if (!gross || !line.product_id) {
                    if (line.online_campaign_id || line.online_discount_amount) {
                        line.update({ discount: 0, ...emptyCampaignValues });
                    }
                    continue;
                }

                const refundedLine = line.refunded_orderline_id;
                if (refundedLine?.online_discount_amount) {
                    const ratio = Math.abs(refundedLine.qty)
                        ? Math.abs(line.qty) / Math.abs(refundedLine.qty)
                        : 0;
                    const discountAmount = round(Math.abs(refundedLine.online_discount_amount) * ratio);
                    const aggregatorAmount = round(
                        Math.abs(refundedLine.aggregator_contribution_amount || 0) * ratio
                    );
                    line.update({ discount: refundedLine.discount });
                    const refundNet = Math.abs(line.priceIncl);
                    line.update({
                        online_campaign_id: refundedLine.online_campaign_id || false,
                        online_aggregator_id: refundedLine.online_aggregator_id || false,
                        online_discount_percent: refundedLine.online_discount_percent,
                        online_discount_amount: discountAmount,
                        aggregator_contribution_amount: aggregatorAmount,
                        company_contribution_amount: round(discountAmount - aggregatorAmount),
                        online_discount_cap_amount: refundedLine.online_discount_cap_amount,
                        cap_application: refundedLine.cap_application,
                        aggregator_commission_percent: refundedLine.aggregator_commission_percent,
                        aggregator_commission_amount: round(
                            (refundNet * refundedLine.aggregator_commission_percent) / 100
                        ),
                        online_campaign_breakdown: refundedLine.online_campaign_breakdown || false,
                    });
                    continue;
                }

                const selected = campaignCandidates(campaigns, order, line.product_id, moment);
                if (!selected.length) {
                    const channelCampaign = activePricelistCampaigns(campaigns, order, moment)[0];
                    if (channelCampaign) {
                        const retainedDiscount = line.online_discount_amount ? 0 : line.discount || 0;
                        if (line.online_discount_amount) {
                            line.update({ discount: retainedDiscount });
                        }
                        const commissionBase = Math.abs(line.priceIncl);
                        const values = {
                            ...emptyCampaignValues,
                            online_campaign_id: channelCampaign,
                            online_aggregator_id: channelCampaign.aggregator_id,
                            aggregator_commission_percent:
                                channelCampaign.aggregator_commission_percent,
                            aggregator_commission_amount: round(
                                (commissionBase * channelCampaign.aggregator_commission_percent) / 100
                            ),
                        };
                        line.update(values);
                    } else if (line.online_campaign_id || line.online_discount_amount) {
                        const values = { ...emptyCampaignValues };
                        if (line.online_discount_amount) {
                            values.discount = 0;
                        }
                        line.update(values);
                    }
                    continue;
                }

                let breakdown = selected.map((campaign) => {
                    const amount =
                        campaign.cap_application === "per_order"
                            ? perOrderAllocations.get(`${line.uuid}:${campaign.id}`) || 0
                            : round(uncappedDiscount(campaign, gross, line.qty));
                    return {
                        campaign_id: campaign.id,
                        name: campaign.name,
                        discount_percent: campaign.discount_percent,
                        discount_amount: amount,
                        aggregator_amount: round(
                            (amount * campaign.aggregator_contribution_percent) / 100
                        ),
                    };
                });
                const rawTotal = breakdown.reduce((sum, item) => sum + item.discount_amount, 0);
                if (rawTotal > Math.abs(gross)) {
                    const factor = Math.abs(gross) / rawTotal;
                    breakdown = breakdown.map((item) => ({
                        ...item,
                        discount_amount: round(item.discount_amount * factor),
                        aggregator_amount: round(item.aggregator_amount * factor),
                    }));
                }
                const discountAmount = round(
                    breakdown.reduce((sum, item) => sum + item.discount_amount, 0)
                );
                const aggregatorAmount = round(
                    breakdown.reduce((sum, item) => sum + item.aggregator_amount, 0)
                );
                const effectivePercent = Math.min(100, (discountAmount / Math.abs(gross)) * 100);
                const nominalPercent = Math.min(
                    100, selected.reduce((sum, campaign) => sum + campaign.discount_percent, 0)
                );
                const primary = selected[0];
                line.update({ discount: effectivePercent });
                const netLine = Math.abs(line.priceIncl);
                line.update({
                    online_campaign_id: primary,
                    online_aggregator_id: primary.aggregator_id,
                    online_discount_percent: nominalPercent,
                    online_discount_amount: discountAmount,
                    aggregator_contribution_amount: aggregatorAmount,
                    company_contribution_amount: round(discountAmount - aggregatorAmount),
                    online_discount_cap_amount: primary.discount_cap_amount,
                    cap_application: primary.cap_application,
                    aggregator_commission_percent: primary.aggregator_commission_percent,
                    aggregator_commission_amount: round(
                        (netLine * primary.aggregator_commission_percent) / 100
                    ),
                    online_campaign_breakdown: breakdown,
                });
            }
        } finally {
            this._onlineCampaignRecomputing = false;
        }
    },

    async pay() {
        this.recomputeOnlineCampaigns(this.getOrder());
        return super.pay(...arguments);
    },
});

patch(PosOrder.prototype, {
    get onlineDiscountTotal() {
        return this.currency.round(
            this.lines.reduce((sum, line) => sum + (line.online_discount_amount || 0), 0)
        );
    },
    get amountBeforeOnlineDiscount() {
        return this.currency.round(
            this.lines.reduce((sum, line) => sum + Math.abs(line.price_unit * line.qty), 0)
        );
    },
});

patch(PosOrderline.prototype, {
    get onlineCampaignLabel() {
        const aggregator = this.online_aggregator_id?.name || "Online";
        return `${aggregator} Campaign`;
    },
    get onlineNetAmount() {
        return this.currency.round(Math.abs(this.displayPrice));
    },
});
