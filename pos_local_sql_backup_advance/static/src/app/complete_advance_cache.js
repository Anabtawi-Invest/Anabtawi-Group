/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

const ORDER_FIELDS = [
    "id",
    "name",
    "partner_id",
    "amount_total",
    "advance_amount",
    "amount_remaining",
    "picking_date",
    "site_service",
    "discount_id",
    "discount_amount",
    "pledge_amount",
    "pledge_count",
];

const LINE_FIELDS = [
    "id",
    "order_id",
    "product_id",
    "product_qty",
    "price_unit",
    "discount",
    "price_subtotal_incl",
    "display_type",
    "sequence",
];

export function completableAdvanceCacheKey(pos) {
    return `pos_advance_complete_cache_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
}

export function readCompletableAdvanceCache(pos) {
    try {
        const raw = localStorage.getItem(completableAdvanceCacheKey(pos));
        const data = JSON.parse(raw || "{}");
        return Array.isArray(data.orders) ? data.orders : [];
    } catch {
        return [];
    }
}

export function writeCompletableAdvanceCache(pos, orders) {
    try {
        localStorage.setItem(
            completableAdvanceCacheKey(pos),
            JSON.stringify({
                orders: orders || [],
                saved_at: new Date().toISOString(),
            })
        );
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save completable advances:", error);
    }
}

export function removeCompletableAdvanceFromCache(pos, advanceId) {
    const orders = readCompletableAdvanceCache(pos).filter((order) => order.id !== advanceId);
    writeCompletableAdvanceCache(pos, orders);
}

function normalizeCachedLine(line) {
    return {
        id: line.id,
        product_id: line.product_id,
        product_name: Array.isArray(line.product_id) ? line.product_id[1] : "",
        product_qty: line.product_qty,
        qty: line.product_qty,
        price_unit: line.price_unit,
        discount: line.discount,
        price_subtotal_incl: line.price_subtotal_incl,
        subtotal: line.price_subtotal_incl,
        display_type: line.display_type,
        sequence: line.sequence,
    };
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.refreshCompletableAdvanceCache();
        return result;
    },

    async refreshCompletableAdvanceCache() {
        const orm = this.data?.orm;
        const configId = this.config?.id;
        if (!orm || !configId) {
            return;
        }
        try {
            const orders = await orm.searchRead(
                "pos.advance.order",
                [
                    ["state", "=", "advance_paid"],
                    ["pos_config_id", "=", configId],
                    ["remaining_pos_order_id", "=", false],
                ],
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
            const orderIds = (orders || []).map((order) => order.id);
            let lines = [];
            if (orderIds.length) {
                lines = await orm.searchRead(
                    "pos.advance.order.line",
                    [["order_id", "in", orderIds]],
                    LINE_FIELDS,
                    { order: "sequence, id" }
                );
            }
            const linesByOrder = {};
            for (const line of lines || []) {
                if (line.display_type || !line.product_id) {
                    continue;
                }
                const orderId = line.order_id?.[0] || line.order_id;
                if (!orderId) {
                    continue;
                }
                (linesByOrder[orderId] ||= []).push(normalizeCachedLine(line));
            }
            const cached = (orders || []).map((order) => ({
                ...order,
                partner_phone: partnerPhoneById[order.partner_id?.[0]] || "",
                lines: linesByOrder[order.id] || [],
                from_server_cache: true,
            }));
            writeCompletableAdvanceCache(this, cached);
            console.info(
                `[LOCAL_BACKUP] Saved ${cached.length} completable advance(s) for offline complete.`
            );
        } catch (error) {
            if (readCompletableAdvanceCache(this).length) {
                console.info(
                    "[LOCAL_BACKUP] Could not refresh completable advances; keeping the last saved list."
                );
            } else {
                console.warn("[LOCAL_BACKUP] Completable advances were not saved:", error);
            }
        }
    },
});
