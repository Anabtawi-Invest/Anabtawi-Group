/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { uuidv4 } from "@point_of_sale/utils";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { ConnectionLostError } from "@web/core/network/rpc";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import {
    localBackupCallObservers,
    serverErrorMessage,
} from "@pos_local_sql_backup/app/pos_store_patch";
import {
    askDeliveryAmount,
    fetchClosingDeliveryPopupData,
    fetchDeliveryAmountPopupData,
    printDeliveryAmountReceipt,
    processDeliveryAmount,
} from "@pos_delivery_amount/app/utils/delivery_amount_flow";

const POPUP_METHODS = {
    get_delivery_amount_popup_data: "cash_delivery",
    get_closing_delivery_popup_data: "closing_delivery",
};

const PROCESS_METHODS = {
    action_process_delivery_amount: "cash_delivery",
    action_process_closing_delivery_amount: "closing_delivery",
};

// Available cash shown in the last delivery popup, per kind of delivery.
const lastPopupData = {};

function deliveryPopupCacheKey(pos) {
    return `pos_delivery_popup_cache_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
}

function readDeliveryPopupCache(pos) {
    try {
        return JSON.parse(localStorage.getItem(deliveryPopupCacheKey(pos)) || "{}");
    } catch {
        return {};
    }
}

function writeDeliveryPopupCache(pos, data) {
    try {
        localStorage.setItem(deliveryPopupCacheKey(pos), JSON.stringify(data || {}));
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save delivery popup cache:", error);
    }
}

function pendingDeliveryKey(pos) {
    return `pos_pending_cash_deliveries_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
}

function readPendingDeliveries(pos) {
    try {
        const list = JSON.parse(localStorage.getItem(pendingDeliveryKey(pos)) || "[]");
        return Array.isArray(list) ? list : [];
    } catch {
        return [];
    }
}

function writePendingDeliveries(pos, rows) {
    try {
        localStorage.setItem(pendingDeliveryKey(pos), JSON.stringify(rows || []));
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save pending cash deliveries:", error);
    }
}

function deliveryObserver({ store, model, method, args, result, error }) {
    if (model !== "pos.session") {
        return;
    }
    if (POPUP_METHODS[method]) {
        if (!error) {
            lastPopupData[POPUP_METHODS[method]] = result || {};
            const cache = readDeliveryPopupCache(store);
            cache[POPUP_METHODS[method]] = result || {};
            writeDeliveryPopupCache(store, cache);
        }
        return;
    }
    const kind = PROCESS_METHODS[method];
    if (!kind) {
        return;
    }
    // Offline path records its own event; sync also records a confirmed copy.
    if (store._skipDeliveryBackupObserver) {
        return;
    }
    const [, amount, reason] = args;
    const popup = lastPopupData[kind] || readDeliveryPopupCache(store)[kind] || {};
    delete lastPopupData[kind];
    const details = {
        delivery_type: kind,
        amount: Number(amount) || 0,
        reason: kind === "cash_delivery" ? reason || "" : "",
        available_cash: popup.max_amount ?? null,
        delivered_before: popup.delivered_total ?? null,
    };
    if (error || !result?.successful) {
        store.recordLocalBackupEvent("cash_delivery_failed", {
            ...details,
            error: error ? serverErrorMessage(error) : result?.message || "Refused by the server",
        });
        return;
    }
    store.recordLocalBackupEvent(kind, { ...details, receipt: result.receipt || null });
    store.syncLocalBackupCashMoves();
}

localBackupCallObservers.push(deliveryObserver);

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.refreshDeliveryPopupCache();
        if (!this._deliveryOnlineBound) {
            this._deliveryOnlineBound = () => this.syncPendingCashDeliveries();
            browser.addEventListener("online", this._deliveryOnlineBound);
        }
        this.syncPendingCashDeliveries();
        return result;
    },

    async refreshDeliveryPopupCache() {
        if (!this.session?.id || !this.data?.call) {
            return;
        }
        const cache = readDeliveryPopupCache(this);
        try {
            const sessionData = await fetchDeliveryAmountPopupData(this);
            cache.cash_delivery = sessionData || {};
            lastPopupData.cash_delivery = sessionData || {};
        } catch (error) {
            console.info("[LOCAL_BACKUP] Could not refresh cash delivery popup cache:", error);
        }
        try {
            const closingData = await fetchClosingDeliveryPopupData(this);
            cache.closing_delivery = closingData || {};
            lastPopupData.closing_delivery = closingData || {};
        } catch (error) {
            console.info("[LOCAL_BACKUP] Could not refresh closing delivery popup cache:", error);
        }
        writeDeliveryPopupCache(this, cache);
    },

    recordLocalCashDelivery({
        delivery_type,
        amount,
        reason = "",
        available_cash = null,
        delivered_before = null,
        queued_offline = true,
    }) {
        const localUuid = uuidv4();
        const kind = delivery_type === "closing_delivery" ? "closing_delivery" : "cash_delivery";
        this.recordLocalBackupEvent(kind, {
            local_only: true,
            queued_offline: Boolean(queued_offline),
            local_uuid: localUuid,
            delivery_type: kind,
            amount: Number(amount) || 0,
            reason: kind === "cash_delivery" ? reason || "" : "",
            available_cash,
            delivered_before,
        });
        const pending = readPendingDeliveries(this);
        pending.push({
            local_uuid: localUuid,
            delivery_type: kind,
            amount: Number(amount) || 0,
            reason: kind === "cash_delivery" ? reason || "" : "",
            created_at: new Date().toISOString(),
        });
        writePendingDeliveries(this, pending);
        // Reduce cached available cash so the next offline popup is closer to reality.
        const cache = readDeliveryPopupCache(this);
        if (cache[kind] && typeof cache[kind].max_amount === "number") {
            cache[kind] = {
                ...cache[kind],
                max_amount: Math.max(0, Number(cache[kind].max_amount) - Number(amount || 0)),
                delivered_total: Number(cache[kind].delivered_total || 0) + Number(amount || 0),
            };
            writeDeliveryPopupCache(this, cache);
            lastPopupData[kind] = cache[kind];
        }
        this.syncPendingCashDeliveries();
        return localUuid;
    },

    async syncPendingCashDeliveries() {
        if (this._pendingDeliverySyncing) {
            return;
        }
        const pending = readPendingDeliveries(this);
        if (!pending.length || !this.session?.id || !this.data?.call) {
            return;
        }
        this._pendingDeliverySyncing = true;
        const remaining = [];
        try {
            for (const row of pending) {
                try {
                    this._skipDeliveryBackupObserver = true;
                    let result;
                    if (row.delivery_type === "closing_delivery") {
                        result = await this.data.call(
                            "pos.session",
                            "action_process_closing_delivery_amount",
                            [this.session.id, row.amount]
                        );
                    } else {
                        result = await this.data.call(
                            "pos.session",
                            "action_process_delivery_amount",
                            [this.session.id, row.amount, row.reason]
                        );
                    }
                    if (!result?.successful) {
                        remaining.push(row);
                        continue;
                    }
                    this.recordLocalBackupEvent(row.delivery_type, {
                        delivery_type: row.delivery_type,
                        amount: row.amount,
                        reason: row.reason || "",
                        local_uuid: row.local_uuid,
                        queued_offline: false,
                        receipt: result.receipt || null,
                    });
                    this.syncLocalBackupCashMoves?.();
                } catch (error) {
                    console.warn("[LOCAL_BACKUP] Could not sync cash delivery:", error);
                    remaining.push(row);
                } finally {
                    this._skipDeliveryBackupObserver = false;
                }
            }
            writePendingDeliveries(this, remaining);
            this.refreshDeliveryPopupCache();
        } finally {
            this._pendingDeliverySyncing = false;
        }
    },
});

patch(ControlButtons.prototype, {
    async onClickDeliveryAmount() {
        let popupData =
            lastPopupData.cash_delivery || readDeliveryPopupCache(this.pos).cash_delivery;
        try {
            popupData = await fetchDeliveryAmountPopupData(this.pos);
        } catch (error) {
            if (!(error instanceof ConnectionLostError) && navigator.onLine !== false) {
                this.notification.add(
                    error?.message || _t("Could not load delivery amount data."),
                    { type: "danger" }
                );
                return;
            }
            if (!popupData?.configured) {
                this.notification.add(
                    _t(
                        "Cash delivery data was not saved on this register. Open the POS online once, then try again offline."
                    ),
                    { type: "warning" }
                );
                return;
            }
        }

        if (!popupData?.configured) {
            this.notification.add(
                _t("Delivery Amount is not configured on this POS."),
                { type: "warning" }
            );
            return;
        }

        const deliveryResult = await askDeliveryAmount(this.dialog, {
            maxAmount: popupData.max_amount,
            deliveredTotal: popupData.delivered_total,
            requireReason: true,
        });
        if (deliveryResult === undefined) {
            return;
        }

        try {
            const response = await processDeliveryAmount(
                this.pos,
                this.dialog,
                deliveryResult.amount,
                deliveryResult.reason
            );
            if (!response?.successful) {
                return;
            }
            await printDeliveryAmountReceipt(this.pos, response.receipt);
            this.notification.add(_t("Delivery Amount processed successfully."), {
                type: "success",
            });
        } catch (error) {
            if (error instanceof ConnectionLostError || navigator.onLine === false) {
                this.pos.recordLocalCashDelivery({
                    delivery_type: "cash_delivery",
                    amount: deliveryResult.amount,
                    reason: deliveryResult.reason,
                    available_cash: popupData.max_amount ?? null,
                    delivered_before: popupData.delivered_total ?? null,
                    queued_offline: true,
                });
                this.notification.add(
                    _t(
                        "Cash delivery saved on this register. It will sync when the connection is back."
                    ),
                    { type: "warning" }
                );
                return;
            }
            throw error;
        }
    },
});
