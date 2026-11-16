/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { uuidv4 } from "@point_of_sale/utils";
import { rpc } from "@web/core/network/rpc";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { captureDangerNotifications } from "@pos_local_sql_backup/app/pos_store_patch";
import { readCakeConfigCache } from "@pos_local_sql_backup_cake/app/cake_config_cache";
import { removeCakeOrderFromCache } from "@pos_local_sql_backup_cake/app/cake_orders_cache";
import { negativeIdFromUuid } from "@pos_local_sql_backup_cake/app/local_cake_store";

function toNumber(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
}

function cakeAction(url, params) {
    const path = typeof url === "string" ? url : "";
    if (!params) {
        return null;
    }
    if (path.includes("/pos/custom_cake/create_order")) {
        return params.pay_later ? "cake_pay_later" : "cake_created";
    }
    if (path.includes("/pos/custom_cake/get_order")) {
        return "cake_loaded";
    }
    return null;
}

function sizeNameFromPayload(pos, payload) {
    const config = readCakeConfigCache(pos);
    const size = (config?.sizes || []).find(
        (row) => Number(row.id) === Number(payload?.cake_size_id)
    );
    return size?.name || "";
}

function componentsFromPayload(pos, payload) {
    const config = readCakeConfigCache(pos);
    const components = [];
    for (const selected of payload?.selected_lines || []) {
        const lineId = selected.category_line_id || selected;
        for (const category of config?.categories || []) {
            const line = (category.lines || []).find((row) => Number(row.id) === Number(lineId));
            if (line) {
                components.push({
                    category: category.name,
                    product_name: line.product_name,
                });
                break;
            }
        }
    }
    return components;
}

patch(PosStore.prototype, {
    serializeOrderForLocalBackup(order) {
        const payload = super.serializeOrderForLocalBackup(...arguments);
        const cakeOrderId = order.pos_cake_order_id || null;
        if (cakeOrderId) {
            payload.cake_order_id = cakeOrderId > 0 ? cakeOrderId : null;
            payload.payload = payload.payload || {};
            payload.payload.cake_order_id = cakeOrderId;
            payload.payload.cake_local_uuid = order.pos_cake_local_uuid || null;
        }
        return payload;
    },
});

patch(ControlButtons.prototype, {
    async _runWithCakeBackup(failedAction, callback) {
        this._cakeCopyRecorded = false;
        try {
            return await this._capturingCakeRequests(async () => {
                const { result, errors } = await captureDangerNotifications(this, callback);
                if (errors.length && !this._cakeCopyRecorded) {
                    this.pos.recordLocalBackupEvent("cake_failed", {
                        failed_action: failedAction,
                        error: errors.join(" | "),
                    });
                }
                return result;
            });
        } finally {
            this.pos._cakeBackupLocalUuid = null;
            this.pos._cakeBackupPrices = null;
            this.pos._cakeBackupPartner = null;
        }
    },

    async _capturingCakeRequests(callback) {
        const originalRpc = rpc._rpc;
        const self = this;
        rpc._rpc = function (url, params = {}, settings = {}) {
            const action = cakeAction(url, params);
            if (action) {
                try {
                    params = self._prepareCakeRpcParams(action, params);
                    self._captureCakeRequest(url, params);
                } catch (error) {
                    console.warn("[LOCAL_BACKUP] Could not copy the cake before sending it:", error);
                }
            }
            return originalRpc.call(this, url, params, settings);
        };
        try {
            return await callback();
        } finally {
            rpc._rpc = originalRpc;
        }
    },

    _prepareCakeRpcParams(action, params) {
        const next = { ...params };
        if (action === "cake_created" || action === "cake_pay_later") {
            next.local_uuid = next.local_uuid || uuidv4();
        }
        return next;
    },

    _captureCakeRequest(url, params) {
        const action = cakeAction(url, params);
        if (!action) {
            return;
        }
        const localUuid = params.local_uuid || this.pos._cakeBackupLocalUuid || uuidv4();
        const partner = this.pos._cakeBackupPartner || null;
        const prices = this.pos._cakeBackupPrices || {};
        if (action === "cake_created" || action === "cake_pay_later") {
            this.pos.saveLocalCakeFromCreate(params, localUuid, {
                partner_name: partner?.name || "",
                partner_phone: partner?.phone || "",
                prices,
                state: "waiting",
                pending_action: "create",
            });
        }
        this.pos.recordLocalBackupEvent(action, {
            local_only: true,
            ...this._cakeSnapshot(action, params, localUuid, partner, prices),
        });
        this.pos._cakeBackupLocalUuid = localUuid;
        this._cakeCopyRecorded = true;
    },

    _cakeSnapshot(action, params, localUuid, partner, prices) {
        if (action === "cake_loaded") {
            return {
                cake: {
                    id: params.order_id || null,
                    local_uuid: localUuid,
                    partner_name: partner?.name || "",
                },
                pos_order_uuid: this._getCurrentOrder?.()?.uuid || null,
            };
        }
        const sizeName = sizeNameFromPayload(this.pos, params);
        const size = (readCakeConfigCache(this.pos)?.sizes || []).find(
            (row) => Number(row.id) === Number(params?.cake_size_id)
        );
        return {
            cake: {
                // Synthetic id so the helper accepts the row before Odoo assigns a real id.
                id: negativeIdFromUuid(localUuid),
                local_uuid: localUuid,
                partner_name: partner?.name || "",
                partner_phone: partner?.phone || "",
                product_name: size?.product_name || "",
                pieces: size?.pieces || 0,
                sugar_paste: Boolean(params.sugar_paste),
                note: params.note || "",
                cake_base_cost: toNumber(prices.cake_base_cost),
                total_components_cost: toNumber(prices.total_components_cost),
                price_before_tax: toNumber(prices.price_before_tax),
                tax_amount: toNumber(prices.tax_amount),
                final_price: toNumber(prices.final_price),
                size_name: sizeName,
            },
            form: {
                phone: partner?.phone || "",
                size_name: sizeNameFromPayload(this.pos, params),
                components: componentsFromPayload(this.pos, params),
            },
            pos_order_uuid: this._getCurrentOrder?.()?.uuid || null,
        };
    },

    _confirmCakeBackupFromServer(result, action, localUuid) {
        if (!result?.id) {
            return;
        }
        if (localUuid) {
            this.pos.markLocalCakeCreated(localUuid, result);
        }
        this.pos.recordLocalBackupEvent(action, {
            cake: {
                id: result.id,
                local_uuid: localUuid || result.local_uuid || null,
                reference: result.name,
                partner_name: result.partner_name,
                product_name: result.product_name,
                pieces: result.pieces,
                sugar_paste: result.sugar_paste,
                note: result.note,
                cake_base_cost: result.cake_base_cost,
                total_components_cost: result.total_components_cost,
                price_before_tax: result.price_before_tax,
                tax_amount: result.tax_amount,
                final_price: result.final_price,
                production_name: result.production_name,
            },
            form: {
                phone: this.pos._cakeBackupPartner?.phone || "",
                components: [],
            },
            pos_order_uuid: this._getCurrentOrder?.()?.uuid || null,
        });
        if (action === "cake_pay_later") {
            this.pos.refreshCakeOrdersCache?.();
        } else if (result.id) {
            removeCakeOrderFromCache(this.pos, result.id);
        }
    },
});
