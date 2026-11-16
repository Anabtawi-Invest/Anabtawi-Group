/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { CakeOrdersListPopup } from "@pos_custom_cake/app/screens/product_screen/control_buttons/cake_button/cake_orders_list_popup";
import { readLocalCakes, negativeIdFromUuid } from "@pos_local_sql_backup_cake/app/local_cake_store";

export function cakeOrdersCacheKey(pos) {
    return `pos_cake_orders_cache_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
}

export function readCakeOrdersCache(pos) {
    try {
        const raw = localStorage.getItem(cakeOrdersCacheKey(pos));
        const data = JSON.parse(raw || "{}");
        return Array.isArray(data.orders) ? data.orders : [];
    } catch {
        return [];
    }
}

export function writeCakeOrdersCache(pos, orders) {
    try {
        localStorage.setItem(
            cakeOrdersCacheKey(pos),
            JSON.stringify({
                orders: orders || [],
                saved_at: new Date().toISOString(),
            })
        );
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save cake orders cache:", error);
    }
}

export function removeCakeOrderFromCache(pos, cakeId) {
    if (!cakeId) {
        return;
    }
    const orders = readCakeOrdersCache(pos).filter((order) => order.id !== cakeId);
    writeCakeOrdersCache(pos, orders);
}

function localWaitingCakeRows(pos) {
    return readLocalCakes(pos)
        .filter(
            (row) =>
                row.pay_later &&
                !row.loaded &&
                (row.state === "waiting_payment" ||
                    row.state === "waiting" ||
                    row.state === "synced" ||
                    row.pending_action === "create")
        )
        .map((row) => ({
            id: row.server_id || negativeIdFromUuid(row.local_uuid),
            name: row.name || `Local ${String(row.local_uuid).slice(0, 8)}`,
            partner_name: row.partner_name || "",
            pieces: row.pieces || 0,
            state: "waiting_payment",
            date_order: row.created_at || "",
            final_price: row.final_price || 0,
            product_name: row.product_name || "",
            note: row.note || "",
            local_uuid: row.local_uuid,
            is_local: !row.server_id,
            from_server_cache: false,
        }));
}

function mergeCakeOrderLists(serverOrders, localOrders) {
    const byKey = new Map();
    for (const order of serverOrders || []) {
        const key = order.local_uuid || `id:${order.id}`;
        byKey.set(key, { ...order, from_server_cache: !order.is_local });
    }
    for (const order of localOrders || []) {
        const key = order.local_uuid || `id:${order.id}`;
        if (!byKey.has(key)) {
            byKey.set(key, order);
        }
    }
    return [...byKey.values()];
}

function filterCakeOrders(orders, query) {
    const q = String(query || "")
        .trim()
        .toLowerCase();
    if (!q) {
        return orders;
    }
    return orders.filter((order) => {
        const name = String(order.name || "").toLowerCase();
        const partner = String(order.partner_name || "").toLowerCase();
        return name.includes(q) || partner.includes(q);
    });
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.refreshCakeOrdersCache();
        return result;
    },

    async refreshCakeOrdersCache() {
        if (!this.config?.id || this.config.enable_custom_cake === false) {
            return [];
        }
        try {
            const orders = await rpc("/pos/custom_cake/search_orders", {
                query: "",
                limit: 100,
            });
            writeCakeOrdersCache(this, orders || []);
            return orders || [];
        } catch (error) {
            console.warn("[LOCAL_BACKUP] Could not refresh cake orders cache:", error);
            return readCakeOrdersCache(this);
        }
    },
});

patch(CakeOrdersListPopup.prototype, {
    async _searchOrders() {
        try {
            this.state.loading = true;
            let serverOrders = [];
            try {
                serverOrders = await rpc("/pos/custom_cake/search_orders", {
                    query: this.state.query,
                    limit: 50,
                });
                if (!this.state.query) {
                    writeCakeOrdersCache(this.props.pos, serverOrders || []);
                }
            } catch (error) {
                serverOrders = filterCakeOrders(readCakeOrdersCache(this.props.pos), this.state.query);
                if (!serverOrders.length) {
                    throw error;
                }
                this.notification.add(
                    "Showing cached cake orders (offline).",
                    { type: "warning" }
                );
            }
            const localOrders = filterCakeOrders(localWaitingCakeRows(this.props.pos), this.state.query);
            this.state.orders = mergeCakeOrderLists(serverOrders, localOrders);
        } catch (error) {
            const localOnly = filterCakeOrders(localWaitingCakeRows(this.props.pos), this.state.query);
            if (localOnly.length) {
                this.state.orders = localOnly;
                this.notification.add(
                    "Showing local cake orders (offline).",
                    { type: "warning" }
                );
            } else {
                this.notification.add(error?.message || "Failed to load cake orders.", {
                    type: "danger",
                });
            }
        } finally {
            this.state.loading = false;
        }
    },
});
