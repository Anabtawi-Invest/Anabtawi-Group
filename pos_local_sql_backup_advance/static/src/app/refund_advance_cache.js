/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

const ORDER_FIELDS = [
    "id",
    "name",
    "partner_id",
    "amount_total",
    "advance_amount",
    "picking_date",
    "pos_config_id",
    "pos_payment_method_id",
    "from_pos_config_id",
];

export function refundableAdvanceCacheKey(pos) {
    return `pos_advance_refund_cache_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
}

export function readRefundableAdvanceCache(pos) {
    try {
        const raw = localStorage.getItem(refundableAdvanceCacheKey(pos));
        const data = JSON.parse(raw || "{}");
        return Array.isArray(data.orders) ? data.orders : [];
    } catch {
        return [];
    }
}

export function writeRefundableAdvanceCache(pos, orders) {
    try {
        localStorage.setItem(
            refundableAdvanceCacheKey(pos),
            JSON.stringify({
                orders: orders || [],
                saved_at: new Date().toISOString(),
            })
        );
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save refundable advances:", error);
    }
}

export function removeRefundableAdvanceFromCache(pos, advanceId) {
    const orders = readRefundableAdvanceCache(pos).filter((order) => order.id !== advanceId);
    writeRefundableAdvanceCache(pos, orders);
}

function refundDomain(configId) {
    return [
        ["state", "=", "advance_paid"],
        ["remaining_pos_order_id", "=", false],
        ["refund_advance_pos_order_id", "=", false],
        ["advance_refund_move_id", "=", false],
        ["advance_payment_created", "=", true],
        "|",
        ["from_pos_config_id", "=", configId],
        "&",
        ["from_pos_config_id", "=", false],
        ["pos_config_id", "=", configId],
    ];
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.refreshRefundableAdvanceCache();
        return result;
    },

    async refreshRefundableAdvanceCache() {
        const orm = this.data?.orm;
        const configId = this.config?.id;
        if (!orm || !configId) {
            return;
        }
        try {
            const orders = await orm.searchRead(
                "pos.advance.order",
                refundDomain(configId),
                ORDER_FIELDS,
                { limit: 500, order: "id desc" }
            );
            const partnerIds = [
                ...new Set((orders || []).map((order) => order.partner_id?.[0]).filter(Boolean)),
            ];
            let partnerPhoneById = {};
            if (partnerIds.length) {
                const partners = await orm.searchRead(
                    "res.partner",
                    [["id", "in", partnerIds]],
                    ["id", "phone"]
                );
                partnerPhoneById = (partners || []).reduce((acc, partner) => {
                    acc[partner.id] = partner.phone || "";
                    return acc;
                }, {});
            }
            const cached = (orders || []).map((order) => ({
                ...order,
                partner_phone: partnerPhoneById[order.partner_id?.[0]] || "",
                payment_method_name: order.pos_payment_method_id?.[1] || "",
                from_server_cache: true,
            }));
            writeRefundableAdvanceCache(this, cached);
            console.info(
                `[LOCAL_BACKUP] Saved ${cached.length} refundable advance(s) for offline refund.`
            );
        } catch (error) {
            if (readRefundableAdvanceCache(this).length) {
                console.info(
                    "[LOCAL_BACKUP] Could not refresh refundable advances; keeping the last saved list."
                );
            } else {
                console.warn("[LOCAL_BACKUP] Refundable advances were not saved:", error);
            }
        }
    },
});
