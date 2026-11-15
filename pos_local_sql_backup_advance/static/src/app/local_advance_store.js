/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { uuidv4 } from "@point_of_sale/utils";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";
import { PosStore } from "@point_of_sale/app/services/pos_store";

function toNumber(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
}

function lineSubtotal(line) {
    return (
        toNumber(line.qty) *
        toNumber(line.price_unit) *
        (1 - toNumber(line.discount) / 100)
    );
}

export function localAdvanceStoreKey(pos) {
    return `pos_local_advances_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
}

export function negativeIdFromUuid(uuid) {
    let hash = 0;
    const text = String(uuid || "");
    for (let i = 0; i < text.length; i++) {
        hash = (hash * 31 + text.charCodeAt(i)) | 0;
    }
    return hash >= 0 ? -hash - 1 : hash;
}

export function readLocalAdvances(pos) {
    try {
        const raw = localStorage.getItem(localAdvanceStoreKey(pos));
        const list = JSON.parse(raw || "[]");
        return Array.isArray(list) ? list : [];
    } catch {
        return [];
    }
}

export function writeLocalAdvances(pos, advances) {
    try {
        localStorage.setItem(localAdvanceStoreKey(pos), JSON.stringify(advances || []));
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save local advances:", error);
    }
}

export function upsertLocalAdvance(pos, advance) {
    const list = readLocalAdvances(pos);
    const index = list.findIndex(
        (row) => row.local_uuid && row.local_uuid === advance.local_uuid
    );
    if (index >= 0) {
        list[index] = { ...list[index], ...advance, updated_at: new Date().toISOString() };
    } else {
        list.unshift({ ...advance, updated_at: new Date().toISOString() });
    }
    writeLocalAdvances(pos, list);
    return list[index >= 0 ? index : 0];
}

export function getLocalAdvance(pos, localUuid) {
    return readLocalAdvances(pos).find((row) => row.local_uuid === localUuid) || null;
}

export function localAdvancesForComplete(pos) {
    return readLocalAdvances(pos)
        .filter((row) => !row.server_completed)
        .filter((row) => ["waiting", "pending_completion", "synced"].includes(row.state))
        .filter((row) => row.state !== "synced" || row.completion)
        .map((row) => ({
            id: row.server_id || negativeIdFromUuid(row.local_uuid),
            local_uuid: row.local_uuid,
            is_local: !row.server_id,
            name: row.name || `Local ${row.local_uuid.slice(0, 8)}`,
            partner_id: row.partner_id
                ? [row.partner_id, row.partner_name || ""]
                : [false, row.partner_name || ""],
            partner_phone: row.partner_phone || "",
            amount_total: toNumber(row.amount_total),
            advance_amount: toNumber(row.advance_amount),
            amount_remaining: toNumber(row.amount_remaining),
            picking_date: row.created_at || "",
            site_service: Boolean(row.create_payload?.site_service),
            discount_id: row.create_payload?.discount_id || false,
            discount_amount: 0,
            pledge_amount: toNumber(row.pledge_amount),
            pledge_count: 0,
            lines: row.lines || [],
            state: row.state,
        }));
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        if (!this._localAdvanceOnlineBound) {
            this._localAdvanceOnlineBound = () => this.syncLocalAdvances();
            browser.addEventListener("online", this._localAdvanceOnlineBound);
        }
        this.syncLocalAdvances();
        return result;
    },

    saveLocalAdvanceFromCreate(params, localUuid, extra = {}) {
        const lines = params.lines || [];
        const total =
            extra.amount_total ??
            lines.reduce((sum, line) => sum + lineSubtotal(line), 0);
        const advanceAmount = toNumber(params.advance_amount);
        return upsertLocalAdvance(this, {
            local_uuid: localUuid,
            server_id: extra.server_id || null,
            name: extra.name || "",
            state: extra.state || "waiting",
            pending_action: extra.pending_action || "create",
            partner_id: params.partner_id || null,
            partner_name: extra.partner_name || "",
            partner_phone: extra.partner_phone || "",
            amount_total: total,
            advance_amount: advanceAmount,
            amount_remaining: Math.max(total - advanceAmount, 0),
            payment_method_name: params.payment_method_name || "",
            create_payload: { ...params, local_uuid: localUuid },
            lines: lines.map((line) => ({
                product_id: line.product_id || null,
                product_name: line.product_name || line.full_product_name || "",
                product_id_name: line.product_name || line.full_product_name || "",
                qty: toNumber(line.qty),
                product_qty: toNumber(line.qty),
                price_unit: toNumber(line.price_unit),
                discount: toNumber(line.discount),
                subtotal: lineSubtotal(line),
                price_subtotal_incl: lineSubtotal(line),
            })),
            completion: null,
            created_at: new Date().toISOString(),
        });
    },

    markLocalAdvanceCreated(localUuid, result = {}) {
        const current = getLocalAdvance(this, localUuid);
        if (!current) {
            return null;
        }
        return upsertLocalAdvance(this, {
            ...current,
            server_id: result.id || current.server_id,
            name: result.name || current.name,
            state: current.completion ? "pending_completion" : "synced",
            pending_action: current.completion ? "complete" : null,
            amount_total: toNumber(result.amount_total, current.amount_total),
            advance_amount: toNumber(result.advance_amount, current.advance_amount),
            amount_remaining: toNumber(result.amount_remaining, current.amount_remaining),
            pledge_amount: toNumber(result.pledge_amount, current.pledge_amount),
        });
    },

    completeLocalAdvance(popupPayload, partnerInfo = {}) {
        const localUuid =
            popupPayload.local_uuid ||
            readLocalAdvances(this).find(
                (row) => negativeIdFromUuid(row.local_uuid) === popupPayload.advance_order_id
            )?.local_uuid;
        if (!localUuid) {
            throw new Error("Local advance not found.");
        }
        const current = getLocalAdvance(this, localUuid);
        if (!current) {
            throw new Error("Local advance not found.");
        }
        const completion = {
            local_uuid: uuidv4(),
            payment_method_id: popupPayload.payment_method_id,
            payment_method_name: popupPayload.payment_method_name || "",
            amount_tendered: toNumber(popupPayload.amount_tendered, current.amount_remaining),
            change_amount: toNumber(popupPayload.change_amount),
            partner_name: partnerInfo.partner_name || current.partner_name,
        };
        const updated = upsertLocalAdvance(this, {
            ...current,
            state: "pending_completion",
            pending_action: current.server_id ? "complete" : "create",
            completion,
            partner_name: completion.partner_name,
        });
        this.recordLocalBackupEvent("advance_completed", {
            local_only: true,
            advance: {
                id: current.server_id || null,
                local_uuid: localUuid,
                reference: current.name || "",
                partner_name: updated.partner_name || "",
                partner_phone: updated.partner_phone || "",
                amount_total: updated.amount_total,
                advance_amount: updated.advance_amount,
                amount_remaining: updated.amount_remaining,
            },
            completion: {
                amount_tendered: completion.amount_tendered,
                remaining_paid: completion.amount_tendered,
                payment_method_name: completion.payment_method_name,
                change_amount: completion.change_amount,
            },
            lines: updated.lines,
        });
        this.syncLocalAdvances();
        return updated;
    },

    async syncLocalAdvances() {
        if (this._localAdvanceSyncing) {
            return;
        }
        const pending = readLocalAdvances(this).filter(
            (row) => row.pending_action === "create" || row.pending_action === "complete"
        );
        if (!pending.length) {
            return;
        }
        this._localAdvanceSyncing = true;
        try {
            for (const row of pending) {
                try {
                    await this._syncOneLocalAdvance(row);
                } catch (error) {
                    console.warn(
                        "[LOCAL_BACKUP] Could not sync local advance",
                        row.local_uuid,
                        error
                    );
                }
            }
        } finally {
            this._localAdvanceSyncing = false;
        }
    },

    async _syncOneLocalAdvance(row) {
        let current = getLocalAdvance(this, row.local_uuid) || row;
        if (current.pending_action === "create" || (!current.server_id && current.create_payload)) {
            const result = await rpc("/pos/create_advance_order", {
                ...current.create_payload,
                local_uuid: current.local_uuid,
            });
            current = this.markLocalAdvanceCreated(current.local_uuid, result) || current;
            // Create may unlock a completion that was confirmed while offline.
            current = getLocalAdvance(this, row.local_uuid) || current;
            this.recordLocalBackupEvent("advance_created", {
                advance: {
                    id: result?.id || null,
                    local_uuid: current.local_uuid,
                    reference: result?.name || "",
                    state: result?.state || "",
                    partner_name: current.partner_name,
                    partner_phone: current.partner_phone,
                    amount_total: result?.amount_total ?? current.amount_total,
                    advance_amount: result?.advance_amount ?? current.advance_amount,
                    amount_tendered: result?.amount_tendered,
                    change_amount: result?.change_amount,
                    amount_remaining: result?.amount_remaining ?? current.amount_remaining,
                    pledge_amount: result?.pledge_amount,
                    payment_method_name: current.payment_method_name,
                },
                lines: current.lines,
            });
        }
        current = getLocalAdvance(this, row.local_uuid) || current;
        if (current.server_id && current.completion && current.pending_action === "complete") {
            const result = await rpc("/pos/complete_advance_order", {
                advance_order_id: current.server_id,
                pos_config_id: this.config.id,
                payment_method_id: current.completion.payment_method_id,
                amount_tendered: current.completion.amount_tendered,
                local_uuid: current.local_uuid,
            });
            upsertLocalAdvance(this, {
                ...current,
                state: "completed_local",
                pending_action: null,
                server_completed: true,
                name: result?.name || current.name,
            });
            this.recordLocalBackupEvent("advance_completed", {
                advance: {
                    id: current.server_id,
                    local_uuid: current.local_uuid,
                    reference: result?.name || current.name,
                    state: result?.state || "",
                    partner_name: result?.partner_name || current.partner_name,
                    partner_phone: result?.partner_phone || current.partner_phone,
                    amount_total: result?.amount_total ?? current.amount_total,
                    advance_amount: result?.advance_amount ?? current.advance_amount,
                },
                completion: {
                    pos_order_name: result?.pos_order_name,
                    remaining_paid: result?.remaining_paid,
                    amount_tendered: result?.remaining_amount_tendered,
                    change_amount: result?.remaining_change_amount,
                    payment_method_name:
                        result?.payment_method_name || current.completion.payment_method_name,
                },
            });
        }
    },
});
