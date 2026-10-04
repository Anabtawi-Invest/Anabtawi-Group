/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";

const { DateTime } = luxon;

const SCAN_INTERVAL_MS = 3000;
const REQUEST_TIMEOUT_MS = 5000;
const BATCH_SIZE = 50;

function safe(getter, fallback = null) {
    try {
        const value = getter();
        return value === undefined ? fallback : value;
    } catch {
        return fallback;
    }
}

function formatLocalDate(value) {
    if (!value) {
        return "";
    }
    const date =
        typeof value === "string" ? DateTime.fromSQL(value, { zone: "utc" }) : DateTime.fromISO(value.toISO?.());
    return date.isValid ? date.toLocal().toFormat("yyyy-MM-dd HH:mm:ss") : String(value);
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
        if (!this.isLocalBackupEnabled || this.localBackup) {
            return;
        }
        this.localBackup = {
            signatures: new Map(),
            deletedQueue: [],
            running: false,
            available: true,
        };
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

    getLocalBackupSignature(order) {
        return [
            order.id,
            order.state,
            order.partner_id?.id || "",
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
            session_name: order.session_id?.name || this.session?.name,
            date_order: formatLocalDate(order.date_order),
            partner_id: order.partner_id?.id || null,
            partner_name: order.partner_id?.name || "",
            cashier: order.employee_id?.name || order.user_id?.name || "",
            state: order.state,
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
    },

    removeOrder(order) {
        if (this.localBackup && order?.uuid && !order.finalized && this.localBackup.signatures.has(order.uuid)) {
            this.localBackup.deletedQueue.push({ uuid: order.uuid });
            this.localBackup.signatures.delete(order.uuid);
        }
        return super.removeOrder(...arguments);
    },
});
