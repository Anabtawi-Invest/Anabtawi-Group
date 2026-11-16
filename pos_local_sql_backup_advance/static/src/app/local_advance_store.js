/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { uuidv4 } from "@point_of_sale/utils";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { removeCompletableAdvanceFromCache } from "@pos_local_sql_backup_advance/app/complete_advance_cache";
import { removeRefundableAdvanceFromCache } from "@pos_local_sql_backup_advance/app/refund_advance_cache";

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

function productIdOf(value) {
    if (!value) {
        return null;
    }
    if (typeof value === "number") {
        return value;
    }
    if (Array.isArray(value)) {
        return value[0] || null;
    }
    return value.id || null;
}

function pledgeUnitAmount(product) {
    if (!product) {
        return 0;
    }
    const pledgeAmount = toNumber(product.pledge_amount);
    if (pledgeAmount > 0) {
        return pledgeAmount;
    }
    return toNumber(product.lst_price ?? product.list_price);
}

/**
 * Mirror the server expand: when Site Service is not checked on the advance,
 * mapped menu products get their pledge products appended for local display.
 * The create payload sent to Odoo stays without these lines so the server does
 * not double-add them on sync.
 */
export function expandAdvanceLinesWithPledges(pos, lines, siteServiceEnabled) {
    const baseLines = Array.isArray(lines) ? lines : [];
    if (siteServiceEnabled || !baseLines.length) {
        return {
            lines: baseLines.map((line) => ({ ...line, subtotal: lineSubtotal(line) })),
            pledge_amount: 0,
        };
    }
    const mappingLines = pos.models?.["pos.site.service.product.line"]?.getAll?.() || [];
    const map = new Map();
    for (const row of mappingLines) {
        const menuId = productIdOf(row.product_id);
        const pledgeId = productIdOf(row.pledge_product_id);
        if (menuId && pledgeId) {
            map.set(menuId, pledgeId);
        }
    }
    const productModel = pos.models?.["product.product"];
    const expanded = [];
    let pledgeAmount = 0;
    for (const line of baseLines) {
        const normalized = {
            ...line,
            qty: toNumber(line.qty),
            price_unit: toNumber(line.price_unit),
            discount: toNumber(line.discount),
            subtotal: lineSubtotal(line),
            is_site_service_pledge_line: Boolean(line.is_site_service_pledge_line),
            is_pledge_line: Boolean(line.is_pledge_line || line.is_site_service_pledge_line),
        };
        expanded.push(normalized);
        if (normalized.is_site_service_pledge_line) {
            continue;
        }
        const pledgeId = map.get(normalized.product_id);
        if (!pledgeId) {
            continue;
        }
        const pledgeProduct = productModel?.get?.(pledgeId);
        const priceUnit = pledgeUnitAmount(pledgeProduct);
        const qty = normalized.qty;
        if (qty <= 0 || priceUnit < 0) {
            continue;
        }
        const subtotal = qty * priceUnit;
        pledgeAmount += subtotal;
        expanded.push({
            product_id: pledgeId,
            product_name:
                pledgeProduct?.display_name ||
                pledgeProduct?.name ||
                `Pledge ${pledgeId}`,
            qty,
            product_qty: qty,
            price_unit: priceUnit,
            discount: 0,
            subtotal,
            price_subtotal_incl: subtotal,
            is_site_service_pledge_line: true,
            is_pledge_line: true,
            source_menu_product_id: normalized.product_id,
        });
    }
    return { lines: expanded, pledge_amount: pledgeAmount };
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

function mapLocalAdvanceRow(row) {
    return {
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
        pledge_count: (row.lines || []).filter(
            (line) => line.is_pledge_line || line.is_site_service_pledge_line
        ).length,
        lines: row.lines || [],
        state: row.state,
        pos_payment_method_id: row.create_payload?.payment_method_id
            ? [row.create_payload.payment_method_id, row.payment_method_name || ""]
            : false,
        payment_method_name: row.payment_method_name || "",
    };
}

export function localAdvancesForComplete(pos) {
    // Only unfinished local creates. Online AOs come from the live/server cache list.
    return readLocalAdvances(pos)
        .filter(
            (row) =>
                !row.server_completed &&
                !row.server_refunded &&
                row.state === "waiting" &&
                row.pending_action !== "refund"
        )
        .map(mapLocalAdvanceRow);
}

export function localAdvancesForRefund(pos) {
    // Waiting local creates (not yet completed/refunded) can be refunded/cancelled locally.
    return readLocalAdvances(pos)
        .filter(
            (row) =>
                !row.server_completed &&
                !row.server_refunded &&
                row.state === "waiting" &&
                row.pending_action !== "complete" &&
                row.pending_action !== "refund"
        )
        .map(mapLocalAdvanceRow);
}

/**
 * Pledge lines from local waiting advances, shaped like Return Pledge rows.
 */
export function localPledgesForReturn(pos, partnerId = null) {
    const rows = [];
    for (const advance of readLocalAdvances(pos)) {
        if (
            advance.server_completed ||
            advance.server_refunded ||
            advance.state === "pending_refund" ||
            advance.pending_action === "refund"
        ) {
            continue;
        }
        const returnedKeys = new Set(advance.returned_local_pledge_keys || []);
        const partnerOk =
            !partnerId ||
            advance.partner_id === partnerId ||
            (!advance.partner_id && !partnerId);
        if (!partnerOk) {
            continue;
        }
        const pledgeLines = (advance.lines || []).filter(
            (line) => line.is_pledge_line || line.is_site_service_pledge_line
        );
        pledgeLines.forEach((line, index) => {
            const productId = productIdOf(line.product_id);
            const key = `${advance.local_uuid}:${productId}:${index}`;
            if (returnedKeys.has(key)) {
                return;
            }
            const qty = toNumber(line.qty ?? line.product_qty);
            const unit = toNumber(line.price_unit);
            const subtotal = toNumber(line.subtotal ?? line.price_subtotal_incl, qty * unit);
            const syntheticId = negativeIdFromUuid(`${advance.local_uuid}-pledge-${index}`);
            rows.push({
                id: syntheticId,
                local_uuid: advance.local_uuid,
                local_pledge_key: key,
                is_local: true,
                from_server_cache: false,
                order_id: [
                    advance.server_id || negativeIdFromUuid(advance.local_uuid),
                    advance.name || `Local ${advance.local_uuid.slice(0, 8)}`,
                ],
                pos_order_id: false,
                partner_id: advance.partner_id
                    ? [advance.partner_id, advance.partner_name || ""]
                    : [false, advance.partner_name || ""],
                partner_phone: advance.partner_phone || "",
                employee_id: false,
                employee_name: "",
                product_id: productId
                    ? [productId, line.product_name || line.product_id_name || ""]
                    : false,
                pledge_qty: qty,
                pledge_amount_unit: unit,
                pledge_subtotal: subtotal,
                pledge_amount: subtotal,
                create_date: advance.created_at || "",
                state: "active",
                return_date: false,
                name: advance.name || `Local ${advance.local_uuid.slice(0, 8)}`,
                employee_amount: 0,
                delivery_amount: 0,
                case_type: "case2",
            });
        });
    }
    return rows;
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
        const siteService = Boolean(params.site_service);
        const { lines, pledge_amount } = expandAdvanceLinesWithPledges(
            this,
            params.lines || [],
            siteService
        );
        const total =
            extra.amount_total ??
            lines.reduce((sum, line) => sum + toNumber(line.subtotal, lineSubtotal(line)), 0);
        const advanceAmount = toNumber(params.advance_amount);
        // Never wipe an offline completion if create is captured again for the same uuid.
        const existing = getLocalAdvance(this, localUuid);
        const keepCompletion = existing?.completion || null;
        const hasPendingComplete = Boolean(keepCompletion && !existing?.server_completed);
        return upsertLocalAdvance(this, {
            local_uuid: localUuid,
            server_id: extra.server_id || existing?.server_id || null,
            name: extra.name || existing?.name || "",
            state: hasPendingComplete
                ? "pending_completion"
                : extra.state || existing?.state || "waiting",
            pending_action: hasPendingComplete
                ? existing?.server_id || extra.server_id
                    ? "complete"
                    : "create"
                : extra.pending_action || "create",
            partner_id: params.partner_id || null,
            partner_name: extra.partner_name || "",
            partner_phone: extra.partner_phone || "",
            amount_total: total,
            advance_amount: advanceAmount,
            amount_remaining: Math.max(total - advanceAmount, 0),
            pledge_amount: toNumber(extra.pledge_amount, pledge_amount),
            payment_method_name: params.payment_method_name || "",
            // Keep original cart lines for sync; server adds pledge lines itself.
            create_payload: { ...params, local_uuid: localUuid },
            lines: lines.map((line) => ({
                product_id: line.product_id || null,
                product_name: line.product_name || line.full_product_name || "",
                product_id_name: line.product_name || line.full_product_name || "",
                qty: toNumber(line.qty),
                product_qty: toNumber(line.qty ?? line.product_qty),
                price_unit: toNumber(line.price_unit),
                discount: toNumber(line.discount),
                subtotal: toNumber(line.subtotal, lineSubtotal(line)),
                price_subtotal_incl: toNumber(
                    line.price_subtotal_incl,
                    toNumber(line.subtotal, lineSubtotal(line))
                ),
                is_site_service_pledge_line: Boolean(line.is_site_service_pledge_line),
                is_pledge_line: Boolean(line.is_pledge_line || line.is_site_service_pledge_line),
                source_menu_product_id: line.source_menu_product_id || null,
            })),
            completion: keepCompletion,
            created_at: existing?.created_at || new Date().toISOString(),
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
        const serverId =
            popupPayload.advance_order_id > 0 ? popupPayload.advance_order_id : null;
        let localUuid =
            popupPayload.local_uuid ||
            readLocalAdvances(this).find(
                (row) =>
                    (serverId && row.server_id === serverId) ||
                    negativeIdFromUuid(row.local_uuid) === popupPayload.advance_order_id
            )?.local_uuid;
        let current = localUuid ? getLocalAdvance(this, localUuid) : null;
        // Online AO taken from the cached complete list while offline.
        if (!current && serverId) {
            localUuid = localUuid || uuidv4();
            current = upsertLocalAdvance(this, {
                local_uuid: localUuid,
                server_id: serverId,
                name: popupPayload.reference || "",
                state: "synced",
                pending_action: null,
                partner_name:
                    partnerInfo.partner_name || popupPayload.partner_name || "",
                partner_phone: popupPayload.partner_phone || "",
                amount_total: toNumber(popupPayload.amount_total),
                advance_amount: toNumber(popupPayload.advance_amount),
                amount_remaining: toNumber(popupPayload.amount_remaining),
                lines: popupPayload.lines || [],
                create_payload: null,
                completion: null,
                created_at: new Date().toISOString(),
            });
        }
        if (!localUuid || !current) {
            throw new Error("Local advance not found.");
        }
        const remainingForComplete = toNumber(
            popupPayload.amount_remaining,
            current.amount_remaining
        );
        const rawTendered = Number(popupPayload.amount_tendered);
        const completion = {
            local_uuid: uuidv4(),
            payment_method_id: popupPayload.payment_method_id,
            payment_method_name: popupPayload.payment_method_name || "",
            // 0 is a valid Number but means "use remaining" for offline complete.
            amount_tendered:
                Number.isFinite(rawTendered) && rawTendered > 0
                    ? rawTendered
                    : remainingForComplete,
            change_amount: toNumber(popupPayload.change_amount),
            partner_name:
                partnerInfo.partner_name ||
                popupPayload.partner_name ||
                current.partner_name,
        };
        const updated = upsertLocalAdvance(this, {
            ...current,
            server_id: current.server_id || serverId,
            name: current.name || popupPayload.reference || "",
            state: "pending_completion",
            pending_action: current.server_id || serverId ? "complete" : "create",
            completion,
            partner_name: completion.partner_name,
            partner_phone: popupPayload.partner_phone || current.partner_phone || "",
            amount_total: toNumber(popupPayload.amount_total, current.amount_total),
            advance_amount: toNumber(popupPayload.advance_amount, current.advance_amount),
            amount_remaining: toNumber(
                popupPayload.amount_remaining,
                current.amount_remaining
            ),
            lines: (popupPayload.lines && popupPayload.lines.length
                ? popupPayload.lines
                : current.lines) || [],
        });
        if (updated.server_id) {
            removeCompletableAdvanceFromCache(this, updated.server_id);
        }
        this.recordLocalBackupEvent("advance_completed", {
            local_only: true,
            advance: {
                id: updated.server_id || null,
                local_uuid: localUuid,
                reference: updated.name || "",
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

    refundLocalAdvance(popupPayload) {
        const serverId =
            popupPayload.advance_order_id > 0 ? popupPayload.advance_order_id : null;
        let localUuid =
            popupPayload.local_uuid ||
            readLocalAdvances(this).find(
                (row) =>
                    (serverId && row.server_id === serverId) ||
                    negativeIdFromUuid(row.local_uuid) === popupPayload.advance_order_id
            )?.local_uuid;
        let current = localUuid ? getLocalAdvance(this, localUuid) : null;
        if (!current && serverId) {
            localUuid = localUuid || uuidv4();
            current = upsertLocalAdvance(this, {
                local_uuid: localUuid,
                server_id: serverId,
                name: popupPayload.reference || "",
                state: "synced",
                pending_action: null,
                partner_name: popupPayload.partner_name || "",
                partner_phone: popupPayload.partner_phone || "",
                amount_total: toNumber(popupPayload.amount_total),
                advance_amount: toNumber(popupPayload.advance_amount),
                lines: [],
                create_payload: null,
                completion: null,
                refund: null,
                created_at: new Date().toISOString(),
            });
        }
        if (!localUuid || !current) {
            throw new Error("Local advance not found for refund.");
        }
        // Never-synced local create: cancel locally; nothing to refund on Odoo.
        if (!current.server_id && current.create_payload) {
            const updated = upsertLocalAdvance(this, {
                ...current,
                state: "cancelled_local",
                pending_action: null,
                server_refunded: true,
                refund: {
                    payment_method_id: popupPayload.payment_method_id,
                    payment_method_name: popupPayload.payment_method_name || "",
                    amount: toNumber(popupPayload.advance_amount, current.advance_amount),
                },
            });
            this.recordLocalBackupEvent("advance_refunded", {
                local_only: true,
                advance: {
                    id: null,
                    local_uuid: localUuid,
                    reference: updated.name || "",
                    partner_name: updated.partner_name || "",
                    partner_phone: updated.partner_phone || "",
                    amount_total: updated.amount_total,
                    advance_amount: updated.advance_amount,
                },
                refund: {
                    amount: updated.refund.amount,
                    payment_method_name: updated.refund.payment_method_name,
                },
            });
            return updated;
        }
        const refund = {
            payment_method_id: popupPayload.payment_method_id,
            payment_method_name: popupPayload.payment_method_name || "",
            amount: toNumber(popupPayload.advance_amount, current.advance_amount),
        };
        const updated = upsertLocalAdvance(this, {
            ...current,
            server_id: current.server_id || serverId,
            name: current.name || popupPayload.reference || "",
            state: "pending_refund",
            pending_action: "refund",
            refund,
            partner_name: popupPayload.partner_name || current.partner_name || "",
            partner_phone: popupPayload.partner_phone || current.partner_phone || "",
            amount_total: toNumber(popupPayload.amount_total, current.amount_total),
            advance_amount: toNumber(popupPayload.advance_amount, current.advance_amount),
        });
        if (updated.server_id) {
            removeRefundableAdvanceFromCache(this, updated.server_id);
            removeCompletableAdvanceFromCache(this, updated.server_id);
        }
        this.recordLocalBackupEvent("advance_refunded", {
            local_only: true,
            advance: {
                id: updated.server_id || null,
                local_uuid: localUuid,
                reference: updated.name || "",
                partner_name: updated.partner_name || "",
                partner_phone: updated.partner_phone || "",
                amount_total: updated.amount_total,
                advance_amount: updated.advance_amount,
            },
            refund: {
                amount: refund.amount,
                payment_method_name: refund.payment_method_name,
            },
        });
        this.syncLocalAdvances();
        return updated;
    },

    markLocalPledgesReturned(pledges) {
        const byUuid = new Map();
        for (const pledge of pledges || []) {
            if (!pledge?.local_uuid || !pledge.local_pledge_key) {
                continue;
            }
            const list = byUuid.get(pledge.local_uuid) || [];
            list.push(pledge.local_pledge_key);
            byUuid.set(pledge.local_uuid, list);
        }
        for (const [localUuid, keys] of byUuid.entries()) {
            const current = getLocalAdvance(this, localUuid);
            if (!current) {
                continue;
            }
            const returned = new Set([
                ...(current.returned_local_pledge_keys || []),
                ...keys,
            ]);
            upsertLocalAdvance(this, {
                ...current,
                returned_local_pledge_keys: [...returned],
            });
        }
    },

    async syncLocalAdvances() {
        if (this._localAdvanceSyncing) {
            return;
        }
        const pending = readLocalAdvances(this).filter(
            (row) =>
                row.pending_action === "create" ||
                row.pending_action === "complete" ||
                row.pending_action === "refund" ||
                // Recover stuck offline completes after create-only sync (older builds).
                (row.completion && !row.server_completed && row.server_id)
        );
        if (!pending.length) {
            await this.syncPendingPledgeReturns?.();
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
            await this.syncPendingPledgeReturns?.();
        } finally {
            this._localAdvanceSyncing = false;
        }
    },

    async _syncOneLocalAdvance(row) {
        let current = getLocalAdvance(this, row.local_uuid) || row;
        if (current.pending_action === "create" || (!current.server_id && current.create_payload)) {
            // Locally cancelled before sync: drop create, nothing to send.
            if (current.server_refunded || current.state === "cancelled_local") {
                return;
            }
            const createPayload = {
                ...(current.create_payload || {}),
                local_uuid: current.local_uuid,
                // Always use the session open now, not the offline snapshot session.
                deposit_pos_session_id: this.session?.id || current.create_payload?.deposit_pos_session_id,
                from_pos_config_id:
                    this.config?.id || current.create_payload?.from_pos_config_id,
            };
            const result = await rpc("/pos/create_advance_order", createPayload);
            current = this.markLocalAdvanceCreated(current.local_uuid, result) || current;
            // Create may unlock a completion that was confirmed while offline.
            current = getLocalAdvance(this, row.local_uuid) || current;
            if (current.completion && !current.server_completed) {
                current = upsertLocalAdvance(this, {
                    ...current,
                    state: "pending_completion",
                    pending_action: "complete",
                    // Prefer server remaining so complete tendered is high enough.
                    amount_remaining: toNumber(
                        result?.amount_remaining,
                        current.amount_remaining
                    ),
                });
            }
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
                keep_pending_complete: Boolean(current.completion),
            });
            this.refreshRefundableAdvanceCache?.();
            this.refreshActivePledgeCache?.();
        }
        current = getLocalAdvance(this, row.local_uuid) || current;
        // Any stored offline completion must sync once the AO exists on the server.
        if (current.server_id && current.completion && !current.server_completed) {
            const pickingConfigId =
                current.create_payload?.pos_config_id || this.config.id;
            let tendered = toNumber(current.completion.amount_tendered);
            const remaining = toNumber(current.amount_remaining);
            if (tendered < remaining) {
                tendered = remaining;
            }
            try {
                const result = await rpc("/pos/complete_advance_order", {
                    advance_order_id: current.server_id,
                    // Must be the Picking POS — server rejects deposit POS when different.
                    pos_config_id: pickingConfigId,
                    payment_method_id: current.completion.payment_method_id,
                    amount_tendered: tendered,
                    local_uuid: current.local_uuid,
                });
                upsertLocalAdvance(this, {
                    ...current,
                    state: "completed_local",
                    pending_action: null,
                    server_completed: true,
                    name: result?.name || current.name,
                });
                removeCompletableAdvanceFromCache(this, current.server_id);
                removeRefundableAdvanceFromCache(this, current.server_id);
                this.refreshCompletableAdvanceCache?.();
                this.refreshRefundableAdvanceCache?.();
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
                            result?.payment_method_name ||
                            current.completion.payment_method_name,
                    },
                });
            } catch (error) {
                // Keep pending so the next online/reload retries completion.
                upsertLocalAdvance(this, {
                    ...current,
                    state: "pending_completion",
                    pending_action: "complete",
                });
                console.warn(
                    "[LOCAL_BACKUP] Could not sync advance completion",
                    current.local_uuid,
                    current.server_id,
                    error
                );
                this.notification?.add?.(
                    _t(
                        "Advance %s deposit synced, but completion is still waiting. Open the Picking POS (or reload) to finish it. %s",
                        current.name || current.server_id,
                        error?.data?.message || error?.message || ""
                    ),
                    { type: "warning", sticky: true }
                );
                throw error;
            }
        }
        current = getLocalAdvance(this, row.local_uuid) || current;
        if (current.server_id && current.refund && current.pending_action === "refund") {
            const orm = this.env?.services?.orm || this.data?.orm;
            if (!orm) {
                throw new Error("ORM not available for refund sync.");
            }
            const result = await orm.call(
                "pos.advance.order",
                "action_refund_advance_payment",
                [[current.server_id]],
                {
                    pos_config_id: this.config.id,
                    pos_payment_method_id: current.refund.payment_method_id,
                    refund_pos_session_id: this.session?.id,
                }
            );
            upsertLocalAdvance(this, {
                ...current,
                state: "refunded_local",
                pending_action: null,
                server_refunded: true,
                name: result?.name || current.name,
            });
            removeRefundableAdvanceFromCache(this, current.server_id);
            removeCompletableAdvanceFromCache(this, current.server_id);
            this.refreshRefundableAdvanceCache?.();
            this.refreshCompletableAdvanceCache?.();
            this.refreshActivePledgeCache?.();
            this.recordLocalBackupEvent("advance_refunded", {
                advance: {
                    id: current.server_id,
                    local_uuid: current.local_uuid,
                    reference: result?.name || current.name,
                    state: result?.state || "",
                    partner_name: current.partner_name,
                    partner_phone: current.partner_phone,
                    amount_total: current.amount_total,
                    advance_amount: current.advance_amount,
                },
                refund: {
                    amount: current.refund.amount,
                    payment_method_name: current.refund.payment_method_name,
                },
            });
        }
    },
});
