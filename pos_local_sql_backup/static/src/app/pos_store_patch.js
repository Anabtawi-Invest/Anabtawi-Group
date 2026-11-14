/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { uuidv4 } from "@point_of_sale/utils";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosData } from "@point_of_sale/app/services/data_service";

const { DateTime } = luxon;

const SCAN_INTERVAL_MS = 3000;
const CASH_MOVES_SYNC_MS = 60000;
const REQUEST_TIMEOUT_MS = 5000;
const BATCH_SIZE = 50;
// Oldest events are dropped beyond this, so a helper that never comes back cannot fill the browser storage.
const MAX_QUEUED_EVENTS = 1000;

/**
 * Functions called after every POS server call (`pos.data.call`), with
 * { store, model, method, args, result, error }. Bridge modules push their own
 * observers here to record server-side actions the order scan cannot see.
 */
export const localBackupCallObservers = [];

let activeStore = null;

export function safe(getter, fallback = null) {
    try {
        const value = getter();
        return value === undefined ? fallback : value;
    } catch {
        return fallback;
    }
}

export function formatLocalDate(value) {
    if (!value) {
        return "";
    }
    const date =
        typeof value === "string" ? DateTime.fromSQL(value, { zone: "utc" }) : DateTime.fromISO(value.toISO?.());
    return date.isValid ? date.toLocal().toFormat("yyyy-MM-dd HH:mm:ss") : String(value);
}

export function serverErrorMessage(error) {
    return error?.data?.arguments?.[0] || error?.data?.message || error?.message || String(error);
}

/**
 * Some POS buttons call the server directly and only report errors as red
 * notifications. Runs `callback` while collecting those messages from
 * `component.notification`, and returns them with the callback result.
 */
export async function captureDangerNotifications(component, callback) {
    const notification = component.notification;
    const errors = [];
    component.notification = {
        ...notification,
        add: (message, options = {}) => {
            if (options.type === "danger") {
                errors.push(String(message));
            }
            return notification.add(message, options);
        },
    };
    try {
        const result = await callback();
        return { result, errors };
    } finally {
        component.notification = notification;
    }
}

function cashMovesObserver({ store, model, method, args, result, error }) {
    if (model !== "pos.session") {
        return;
    }
    if (method === "try_cash_in_out") {
        const [, type, amount, reason] = args;
        if (error) {
            store.recordLocalBackupEvent("cash_move_failed", {
                move_type: type,
                amount,
                reason,
                error: serverErrorMessage(error),
            });
            return;
        }
        // Offline, the POS queues the call for later and resolves it with undefined.
        store.recordLocalBackupEvent("cash_move", {
            move_type: type,
            amount,
            reason,
            queued_offline: result === undefined,
            result: result ?? null,
        });
        store.syncLocalBackupCashMoves();
    } else if (method === "delete_cash_in_out" && !error) {
        store.recordLocalBackupEvent("cash_move_deleted", { statement_line_id: args[1] });
        store.syncLocalBackupCashMoves();
    }
}

localBackupCallObservers.push(cashMovesObserver);

// Odoo names a new session "/" and renames it when the opening cash is confirmed,
// without telling the open POS page.
function sessionNameObserver({ store, model, method, result, error }) {
    if (model === "pos.session" && method === "set_opening_control" && !error && result !== undefined) {
        store.refreshLocalBackupSessionName();
    }
}

localBackupCallObservers.push(sessionNameObserver);

patch(PosData.prototype, {
    async call(model, method, args = []) {
        let result;
        try {
            result = await super.call(...arguments);
        } catch (error) {
            notifyLocalBackupObservers({ model, method, args, error });
            throw error;
        }
        notifyLocalBackupObservers({ model, method, args, result });
        return result;
    },
});

function notifyLocalBackupObservers(call) {
    const store = activeStore;
    if (!store?.localBackup) {
        return;
    }
    for (const observer of localBackupCallObservers) {
        try {
            observer({ store, ...call });
        } catch (error) {
            console.warn("[LOCAL_BACKUP] Could not record a server action:", error);
        }
    }
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.startLocalBackup();
        return result;
    },

    get isLocalBackupEnabled() {
        return Boolean(
            this.config?.local_backup_enabled &&
                this.config.local_backup_url &&
                this.config.local_backup_api_key
        );
    },

    startLocalBackup() {
        if (this.localBackup) {
            return;
        }
        if (!this.isLocalBackupEnabled) {
            console.info(
                `[LOCAL_BACKUP] disabled on POS config "${this.config?.name}" ` +
                    `(local_backup_enabled=${Boolean(this.config?.local_backup_enabled)}, ` +
                    `url=${this.config?.local_backup_url ? "set" : "missing"}, ` +
                    `api_key=${this.config?.local_backup_api_key ? "set" : "missing"})`
            );
            return;
        }
        console.info(`[LOCAL_BACKUP] enabled - sending orders to ${this.config.local_backup_url}`);
        this.localBackup = {
            signatures: new Map(),
            deletedQueue: [],
            running: false,
            available: true,
            eventsFlushing: false,
            cashMovesSignature: null,
            lastCashMovesSync: 0,
            sessionName: null,
        };
        activeStore = this;
        this.checkLocalBackupHealth();
        this.localBackup.interval = setInterval(() => this.runLocalBackup(), SCAN_INTERVAL_MS);
    },

    async localBackupRequest(path, method = "GET", body = undefined) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
        try {
            const response = await fetch(`${this.config.local_backup_url.replace(/\/+$/, "")}${path}`, {
                method,
                headers: {
                    "Content-Type": "application/json",
                    "X-Api-Key": this.config.local_backup_api_key,
                },
                body: body === undefined ? undefined : JSON.stringify(body),
                signal: controller.signal,
            });
            if (!response.ok) {
                throw new Error(`Local backup helper answered ${response.status}`);
            }
            return await response.json();
        } finally {
            clearTimeout(timeout);
        }
    },

    async checkLocalBackupHealth() {
        try {
            const health = await this.localBackupRequest("/api/health");
            this.setLocalBackupAvailable(true);
            if (!health.encrypted) {
                console.warn("[LOCAL_BACKUP] The local database is not encrypted (development mode).");
            }
        } catch (error) {
            this.setLocalBackupAvailable(false, error);
        }
    },

    setLocalBackupAvailable(available, error = null) {
        const state = this.localBackup;
        if (state.available === available) {
            return;
        }
        state.available = available;
        if (available) {
            console.info("[LOCAL_BACKUP] Helper reachable again, resuming local backup.");
            this.notification.add(_t("Local order backup is working again."), { type: "success" });
        } else {
            console.warn("[LOCAL_BACKUP] Helper not reachable:", error);
            this.notification.add(
                _t(
                    "The local order backup service is not running on this computer. Sales continue normally; orders will be copied when it is back."
                ),
                { type: "warning", sticky: true }
            );
        }
    },

    // -- session name ------------------------------------------------------------

    get localBackupSessionName() {
        return this.localBackup?.sessionName || this.session?.name || "";
    },

    localBackupSessionNameOf(session) {
        return session?.id === this.session?.id ? this.localBackupSessionName : session?.name || "";
    },

    async refreshLocalBackupSessionName() {
        const state = this.localBackup;
        if (!state || !this.session?.id || this.session.state === "opening_control") {
            return;
        }
        let records;
        try {
            records = await this.data.orm.read("pos.session", [this.session.id], ["name"]);
        } catch {
            return;
        }
        const name = records?.[0]?.name;
        if (!name || name === "/" || name === state.sessionName) {
            return;
        }
        state.sessionName = name;
        // Send the orders again so they carry the real name.
        state.signatures.clear();
        console.info(`[LOCAL_BACKUP] session name is now ${name}`);
    },

    // -- events (actions done on the server: advances, cakes, cash moves...) --

    get localBackupEventsKey() {
        return `pos_local_backup_events_${odoo.info?.db || ""}_${this.config.id}`;
    },

    readLocalBackupEvents() {
        try {
            const queue = JSON.parse(localStorage.getItem(this.localBackupEventsKey) || "[]");
            return Array.isArray(queue) ? queue : [];
        } catch {
            return [];
        }
    },

    writeLocalBackupEvents(queue) {
        try {
            localStorage.setItem(this.localBackupEventsKey, JSON.stringify(queue.slice(-MAX_QUEUED_EVENTS)));
        } catch (error) {
            console.warn("[LOCAL_BACKUP] Cannot keep the event in the browser storage:", error);
        }
    },

    /**
     * Queue an event for the helper. Events survive a page reload and are sent
     * in order as soon as the helper answers.
     */
    recordLocalBackupEvent(action, data = {}) {
        if (!this.isLocalBackupEnabled) {
            return;
        }
        const event = {
            event_uuid: uuidv4(),
            action,
            ts: DateTime.now().toFormat("yyyy-MM-dd HH:mm:ss"),
            config_id: this.config.id,
            config_name: this.config.name,
            session_id: this.session?.id || null,
            session_name: this.localBackupSessionName,
            cashier: this.getCashier?.()?.name || this.user?.name || "",
            ...data,
        };
        this.writeLocalBackupEvents([...this.readLocalBackupEvents(), event]);
        console.info(`[LOCAL_BACKUP] event ${action}`, event);
        this.flushLocalBackupEvents();
    },

    async flushLocalBackupEvents() {
        const state = this.localBackup;
        if (!state || state.eventsFlushing) {
            return;
        }
        const batch = this.readLocalBackupEvents().slice(0, BATCH_SIZE);
        if (!batch.length) {
            return;
        }
        state.eventsFlushing = true;
        try {
            const result = await this.localBackupRequest("/api/events", "POST", { events: batch });
            const sent = new Set(batch.map((event) => event.event_uuid));
            this.writeLocalBackupEvents(this.readLocalBackupEvents().filter((event) => !sent.has(event.event_uuid)));
            if (result?.errors) {
                console.warn(`[LOCAL_BACKUP] Helper rejected ${result.errors} event(s), see its logs screen.`);
            }
        } catch (error) {
            if (state.available) {
                console.warn(`[LOCAL_BACKUP] ${batch.length} event(s) waiting for the helper:`, error);
            }
        } finally {
            state.eventsFlushing = false;
        }
    },

    // -- cash moves ------------------------------------------------------------

    /**
     * The session's cash in/out list also contains moves added from the Odoo
     * backend, so it is read regularly and sent when it changes.
     */
    async syncLocalBackupCashMoves() {
        const state = this.localBackup;
        if (!state || !this.session?.id) {
            return;
        }
        state.lastCashMovesSync = Date.now();
        let moves;
        try {
            moves = await this.data.orm.call("pos.session", "get_cash_in_out_list", [this.session.id]);
        } catch {
            return;
        }
        const normalized = (moves || []).map((move) => ({
            id: move.id,
            name: move.name || "",
            amount: move.amount,
            date: formatLocalDate(move.date),
            cashier_name: move.cashier_name || "",
        }));
        const signature = JSON.stringify(normalized);
        if (signature === state.cashMovesSignature) {
            return;
        }
        state.cashMovesSignature = signature;
        this.recordLocalBackupEvent("cash_moves_snapshot", { moves: normalized });
    },

    // -- orders ------------------------------------------------------------------

    getLocalBackupSignature(order) {
        return [
            order.id,
            order.state,
            order.partner_id?.id || "",
            order.fiscal_position_id?.id || "",
            order.lines.map((l) => `${l.uuid}:${l.qty}:${l.price_unit}:${l.discount}`).join(","),
            order.payment_ids.map((p) => `${p.uuid}:${p.amount}`).join(","),
        ].join("|");
    },

    serializeOrderForLocalBackup(order) {
        const models = this.models;
        return {
            uuid: order.uuid,
            pos_reference: order.pos_reference || "",
            name: order.name || "",
            config_id: this.config.id,
            config_name: this.config.name,
            session_id: order.session_id?.id || this.session?.id,
            session_name: order.session_id
                ? this.localBackupSessionNameOf(order.session_id)
                : this.localBackupSessionName,
            date_order: formatLocalDate(order.date_order),
            partner_id: order.partner_id?.id || null,
            partner_name: order.partner_id?.name || "",
            cashier: order.employee_id?.name || order.user_id?.name || "",
            state: order.state,
            fiscal_position: order.fiscal_position_id?.display_name || order.fiscal_position_id?.name || "",
            amount_total: safe(() => order.priceIncl, order.amount_total),
            amount_tax: safe(() => order.amountTaxes, order.amount_tax),
            amount_paid: safe(() => order.amountPaid, order.amount_paid),
            amount_return: order.finalized ? order.amount_return : safe(() => order.change, 0),
            server_id: order.isSynced ? order.id : null,
            lines: order.lines.map((line) => ({
                uuid: line.uuid,
                product_id: line.product_id?.id || null,
                product_name: safe(() => line.getFullProductName(), line.product_id?.display_name || ""),
                qty: line.qty,
                price_unit: line.price_unit,
                discount: line.discount,
                price_subtotal: safe(() => line.priceExcl, line.price_subtotal),
                price_subtotal_incl: safe(() => line.priceIncl, line.price_subtotal_incl),
            })),
            payments: order.payment_ids.map((payment) => ({
                uuid: payment.uuid,
                payment_method_id: payment.payment_method_id?.id || null,
                payment_method_name: payment.payment_method_id?.name || "",
                amount: payment.amount,
                payment_date: formatLocalDate(payment.payment_date),
            })),
            payload: {
                order: models["pos.order"].serializeForIndexedDB(order),
                lines: order.lines.map((l) => models["pos.order.line"].serializeForIndexedDB(l)),
                payments: order.payment_ids.map((p) => models["pos.payment"].serializeForIndexedDB(p)),
            },
        };
    },

    async runLocalBackup() {
        const state = this.localBackup;
        if (!state || state.running) {
            return;
        }
        state.running = true;
        try {
            const changed = [];
            for (const order of this.models["pos.order"].getAll()) {
                // Empty draft orders are created all the time by the POS; nothing to back up yet.
                if (!order.uuid || (!order.finalized && !order.lines.length && !order.payment_ids.length)) {
                    continue;
                }
                const signature = this.getLocalBackupSignature(order);
                if (state.signatures.get(order.uuid) !== signature) {
                    changed.push({ order, signature });
                }
            }

            for (let i = 0; i < changed.length; i += BATCH_SIZE) {
                const batch = changed.slice(i, i + BATCH_SIZE);
                const payload = batch.map(({ order }) => this.serializeOrderForLocalBackup(order));
                const result = await this.localBackupRequest("/api/orders", "POST", { orders: payload });
                for (const { order, signature } of batch) {
                    state.signatures.set(order.uuid, signature);
                }
                if (result.errors) {
                    console.warn(`[LOCAL_BACKUP] Helper rejected ${result.errors} order(s), see its logs screen.`);
                }
            }

            if (state.deletedQueue.length) {
                const deleted = [...state.deletedQueue];
                await this.localBackupRequest("/api/orders/deleted", "POST", { orders: deleted });
                state.deletedQueue.splice(0, deleted.length);
            }
            this.setLocalBackupAvailable(true);
        } catch (error) {
            this.setLocalBackupAvailable(false, error);
        } finally {
            state.running = false;
        }
        await this.flushLocalBackupEvents();
        if (Date.now() - state.lastCashMovesSync >= CASH_MOVES_SYNC_MS) {
            if (!state.sessionName && (this.session?.name || "/") === "/") {
                await this.refreshLocalBackupSessionName();
            }
            this.syncLocalBackupCashMoves();
        }
    },

    removeOrder(order) {
        if (this.localBackup && order?.uuid && !order.finalized && this.localBackup.signatures.has(order.uuid)) {
            this.localBackup.deletedQueue.push({ uuid: order.uuid });
            this.localBackup.signatures.delete(order.uuid);
        }
        return super.removeOrder(...arguments);
    },
});
