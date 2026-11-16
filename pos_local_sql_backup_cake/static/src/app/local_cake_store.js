/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { readCakeConfigCache } from "@pos_local_sql_backup_cake/app/cake_config_cache";

function removeCakeOrderFromCache(pos, cakeId) {
    if (!cakeId) {
        return;
    }
    try {
        const key = `pos_cake_orders_cache_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
        const data = JSON.parse(localStorage.getItem(key) || "{}");
        const orders = (Array.isArray(data.orders) ? data.orders : []).filter(
            (order) => order.id !== cakeId
        );
        localStorage.setItem(
            key,
            JSON.stringify({ orders, saved_at: new Date().toISOString() })
        );
    } catch {
        // ignore cache cleanup failures
    }
}

function toNumber(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
}

export function localCakeStoreKey(pos) {
    return `pos_local_cakes_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
}

export function negativeIdFromUuid(uuid) {
    let hash = 0;
    const text = String(uuid || "");
    for (let i = 0; i < text.length; i++) {
        hash = (hash * 31 + text.charCodeAt(i)) | 0;
    }
    return hash >= 0 ? -hash - 1 : hash;
}

export function readLocalCakes(pos) {
    try {
        const raw = localStorage.getItem(localCakeStoreKey(pos));
        const list = JSON.parse(raw || "[]");
        return Array.isArray(list) ? list : [];
    } catch {
        return [];
    }
}

export function writeLocalCakes(pos, cakes) {
    try {
        localStorage.setItem(localCakeStoreKey(pos), JSON.stringify(cakes || []));
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save local cakes:", error);
    }
}

export function getLocalCake(pos, localUuid) {
    return readLocalCakes(pos).find((row) => row.local_uuid === localUuid) || null;
}

export function upsertLocalCake(pos, cake) {
    if (!cake?.local_uuid) {
        return null;
    }
    const list = readLocalCakes(pos).filter((row) => row.local_uuid !== cake.local_uuid);
    const next = { ...cake, updated_at: new Date().toISOString() };
    list.unshift(next);
    writeLocalCakes(pos, list.slice(0, 200));
    return next;
}

function resolveSizeFromCache(pos, cakeSizeId) {
    const config = readCakeConfigCache(pos);
    const size = (config?.sizes || []).find((row) => Number(row.id) === Number(cakeSizeId));
    return size || null;
}

function buildFormComponents(pos, selectedLines) {
    const config = readCakeConfigCache(pos);
    const components = [];
    for (const selected of selectedLines || []) {
        const lineId = selected.category_line_id || selected;
        for (const category of config?.categories || []) {
            const line = (category.lines || []).find((row) => Number(row.id) === Number(lineId));
            if (line) {
                components.push({
                    category: category.name,
                    product_name: line.product_name,
                    product_id: line.product_id,
                });
                break;
            }
        }
    }
    return components;
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        if (!this._localCakeOnlineBound) {
            this._localCakeOnlineBound = () => this.syncLocalCakes();
            browser.addEventListener("online", this._localCakeOnlineBound);
        }
        this.syncLocalCakes();
        return result;
    },

    async pay(...args) {
        // Cake create must land in Odoo before a paid ticket with pos_cake_order_id.
        await this.syncLocalCakes();
        return await super.pay(...args);
    },

    async validateOrderFast(...args) {
        await this.syncLocalCakes();
        return await super.validateOrderFast(...args);
    },

    saveLocalCakeFromCreate(payload, localUuid, extra = {}) {
        const existing = getLocalCake(this, localUuid);
        const size = resolveSizeFromCache(this, payload.cake_size_id);
        const prices = extra.prices || {};
        return upsertLocalCake(this, {
            local_uuid: localUuid,
            server_id: extra.server_id || existing?.server_id || null,
            name: extra.name || existing?.name || "",
            state: extra.state || existing?.state || "waiting",
            pending_action: extra.pending_action || existing?.pending_action || "create",
            pay_later: Boolean(payload.pay_later),
            loaded: Boolean(existing?.loaded),
            partner_id: payload.partner_id || null,
            partner_name: extra.partner_name || existing?.partner_name || "",
            partner_phone: extra.partner_phone || existing?.partner_phone || "",
            product_id: size?.product_id || extra.product_id || existing?.product_id || null,
            product_name: size?.product_name || extra.product_name || existing?.product_name || "",
            size_name: size?.name || extra.size_name || existing?.size_name || "",
            pieces: size?.pieces || extra.pieces || existing?.pieces || 0,
            sugar_paste: Boolean(payload.sugar_paste),
            note: payload.note || "",
            cake_base_cost: toNumber(prices.cake_base_cost, existing?.cake_base_cost),
            total_components_cost: toNumber(
                prices.total_components_cost,
                existing?.total_components_cost
            ),
            price_before_tax: toNumber(prices.price_before_tax, existing?.price_before_tax),
            tax_amount: toNumber(prices.tax_amount, existing?.tax_amount),
            final_price: toNumber(prices.final_price, existing?.final_price),
            create_payload: { ...payload, local_uuid: localUuid },
            form_components: buildFormComponents(this, payload.selected_lines),
            pos_order_uuid: extra.pos_order_uuid || existing?.pos_order_uuid || null,
            created_at: existing?.created_at || new Date().toISOString(),
        });
    },

    markLocalCakeCreated(localUuid, result = {}) {
        const current = getLocalCake(this, localUuid);
        if (!current) {
            return null;
        }
        const updated = upsertLocalCake(this, {
            ...current,
            server_id: result.id || current.server_id,
            name: result.name || current.name,
            state: current.pay_later && !current.loaded ? "waiting_payment" : "synced",
            pending_action: null,
            product_id: result.product_id || current.product_id,
            product_name: result.product_name || current.product_name,
            pieces: result.pieces || current.pieces,
            production_id: result.production_id || current.production_id || null,
            production_name: result.production_name || current.production_name || "",
            price_before_tax: toNumber(result.price_before_tax, current.price_before_tax),
            tax_amount: toNumber(result.tax_amount, current.tax_amount),
            final_price: toNumber(result.final_price, current.final_price),
            cake_base_cost: toNumber(result.cake_base_cost, current.cake_base_cost),
            total_components_cost: toNumber(
                result.total_components_cost,
                current.total_components_cost
            ),
        });
        this._relinkOrdersToSyncedCake(updated);
        return updated;
    },

    markLocalCakeLoaded(localUuid, posOrderUuid = null) {
        const current = getLocalCake(this, localUuid);
        if (!current) {
            return null;
        }
        return upsertLocalCake(this, {
            ...current,
            loaded: true,
            state: "in_order",
            pos_order_uuid: posOrderUuid || current.pos_order_uuid,
        });
    },

    _relinkOrdersToSyncedCake(cake) {
        if (!cake?.server_id || !cake.local_uuid) {
            return;
        }
        const localId = negativeIdFromUuid(cake.local_uuid);
        const orders = this.models?.["pos.order"]?.getAll?.() || [];
        for (const order of orders) {
            if (Number(order.pos_cake_order_id) === localId) {
                order.setPosCakeOrderId(cake.server_id, cake.product_id);
            }
        }
    },

    localCakeAsPosResult(localUuid) {
        const cake = getLocalCake(this, localUuid);
        if (!cake) {
            return null;
        }
        return {
            id: cake.server_id || negativeIdFromUuid(cake.local_uuid),
            name: cake.name || `Local ${String(cake.local_uuid).slice(0, 8)}`,
            state: cake.state || "waiting_payment",
            partner_id: cake.partner_id,
            partner_name: cake.partner_name,
            product_id: cake.product_id,
            product_name: cake.product_name,
            pieces: cake.pieces,
            sugar_paste: cake.sugar_paste,
            cake_base_cost: cake.cake_base_cost,
            total_components_cost: cake.total_components_cost,
            price_before_tax: cake.price_before_tax,
            tax_amount: cake.tax_amount,
            final_price: cake.final_price,
            production_id: cake.production_id || false,
            production_name: cake.production_name || false,
            note: cake.note || "",
            local_uuid: cake.local_uuid,
            is_local: !cake.server_id,
        };
    },

    async syncLocalCakes() {
        if (this._localCakeSyncing) {
            return;
        }
        const pending = readLocalCakes(this).filter((row) => row.pending_action === "create");
        if (!pending.length) {
            return;
        }
        this._localCakeSyncing = true;
        try {
            for (const row of pending) {
                try {
                    await this._syncOneLocalCake(row);
                } catch (error) {
                    console.warn("[LOCAL_BACKUP] Could not sync local cake", row.local_uuid, error);
                    this.notification?.add?.(
                        _t("Custom cake sync failed: %s", error?.message || String(error)),
                        { type: "warning", sticky: true }
                    );
                }
            }
        } finally {
            this._localCakeSyncing = false;
        }
    },

    async _syncOneLocalCake(row) {
        let current = getLocalCake(this, row.local_uuid) || row;
        if (current.pending_action !== "create" && current.server_id) {
            return current;
        }
        const createPayload = {
            ...(current.create_payload || {}),
            local_uuid: current.local_uuid,
            pos_config_id: this.config?.id || current.create_payload?.pos_config_id,
            pos_session_id: this.session?.id || current.create_payload?.pos_session_id || false,
            upload_session_token: "",
        };
        const result = await rpc("/pos/custom_cake/create_order", createPayload);
        current = this.markLocalCakeCreated(current.local_uuid, result) || current;
        if (current.server_id) {
            removeCakeOrderFromCache(this, negativeIdFromUuid(current.local_uuid));
        }
        const action = current.pay_later && !current.loaded ? "cake_pay_later" : "cake_created";
        this.recordLocalBackupEvent(action, {
            cake: {
                id: result?.id || current.server_id,
                local_uuid: current.local_uuid,
                reference: result?.name || current.name,
                partner_name: current.partner_name,
                partner_phone: current.partner_phone,
                product_name: result?.product_name || current.product_name,
                pieces: result?.pieces || current.pieces,
                sugar_paste: current.sugar_paste,
                note: current.note,
                cake_base_cost: result?.cake_base_cost ?? current.cake_base_cost,
                total_components_cost:
                    result?.total_components_cost ?? current.total_components_cost,
                price_before_tax: result?.price_before_tax ?? current.price_before_tax,
                tax_amount: result?.tax_amount ?? current.tax_amount,
                final_price: result?.final_price ?? current.final_price,
                production_name: result?.production_name || "",
                size_name: current.size_name,
            },
            form: {
                phone: current.partner_phone,
                size_name: current.size_name,
                components: current.form_components || [],
            },
            pos_order_uuid: current.pos_order_uuid || null,
        });
        this.refreshCakeOrdersCache?.();
        return current;
    },
});
