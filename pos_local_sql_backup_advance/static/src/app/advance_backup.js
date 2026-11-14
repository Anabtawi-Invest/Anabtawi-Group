/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { uuidv4 } from "@point_of_sale/utils";
import { browser } from "@web/core/browser/browser";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { captureDangerNotifications } from "@pos_local_sql_backup/app/pos_store_patch";

function toNumber(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
}

function receiptLines(lines) {
    return (lines || []).map((line) => ({
        product_id: line.product_id || null,
        product_name: line.name || "",
        qty: toNumber(line.qty),
        discount: toNumber(line.discount),
        subtotal: toNumber(line.subtotal),
        is_pledge_line: Boolean(line.isPledgeLine),
    }));
}

function requestUrl(url) {
    return typeof url === "string" ? url : url?.url || "";
}

function requestParams(body) {
    if (typeof body !== "string") {
        return null;
    }
    try {
        return JSON.parse(body)?.params || null;
    } catch {
        return null;
    }
}

// The advance button calls Odoo directly. The request body is the form the
// cashier already confirmed, so it can be copied before the network answers.
function advanceAction(url, params) {
    const path = requestUrl(url);
    if (!params) {
        return null;
    }
    if (path.includes("/pos/create_advance_order")) {
        return "advance_created";
    }
    if (path.includes("/pos/complete_advance_order")) {
        return "advance_completed";
    }
    if (
        path.includes("action_refund_advance_payment") ||
        params.method === "action_refund_advance_payment"
    ) {
        return "advance_refunded";
    }
    return null;
}

function lineSubtotal(line) {
    return (
        toNumber(line.qty) *
        toNumber(line.price_unit) *
        (1 - toNumber(line.discount) / 100)
    );
}

const LEGACY_ACTIONS = {
    created: "advance_created",
    completed: "advance_completed",
    refunded: "advance_refunded",
    failed: "advance_failed",
};

patch(PosStore.prototype, {
    startLocalBackup() {
        super.startLocalBackup(...arguments);
        if (this.localBackup) {
            this.moveLegacyAdvanceQueue();
        }
    },

    // A confirmation can be queued while the first copy is still being sent.
    // Keep sending until a batch fails or the queue is empty.
    async flushLocalBackupEvents() {
        const before = this.readLocalBackupEvents().length;
        await super.flushLocalBackupEvents(...arguments);
        const after = this.readLocalBackupEvents().length;
        if (after && after < before && !this.localBackup?.eventsFlushing) {
            await this.flushLocalBackupEvents();
        }
    },

    // Version 1.1 kept advance events in a queue of their own.
    moveLegacyAdvanceQueue() {
        const legacyKey = `pos_local_backup_advances_${odoo.info?.db || ""}_${this.config.id}`;
        try {
            const legacy = JSON.parse(localStorage.getItem(legacyKey) || "[]");
            if (Array.isArray(legacy) && legacy.length) {
                const events = legacy.map((event) => ({
                    ...event,
                    action: LEGACY_ACTIONS[event.action] || event.action,
                }));
                this.writeLocalBackupEvents([...events, ...this.readLocalBackupEvents()]);
            }
            localStorage.removeItem(legacyKey);
        } catch (error) {
            console.warn("[LOCAL_BACKUP] Could not move the old advance events:", error);
        }
    },
});

patch(ControlButtons.prototype, {
    async _runWithAdvanceBackup(failedAction, callback) {
        this._advanceCopyRecorded = false;
        try {
            return await this._capturingAdvanceRequests(async () => {
                const { result, errors } = await captureDangerNotifications(this, callback);
                // A full copy was already stored from the form. The short failure
                // note would only repeat the customer name.
                if (errors.length && !this._advanceCopyRecorded) {
                    const partner = this._getOrderPartner?.(this._getCurrentOrder?.());
                    this.pos.recordLocalBackupEvent("advance_failed", {
                        failed_action: failedAction,
                        error: errors.join(" | "),
                        advance: failedAction === "create" ? { partner_name: partner?.name || "" } : {},
                    });
                }
                return result;
            });
        } finally {
            this.pos._advanceBackupLocalUuid = null;
        }
    },

    // Watch the Odoo call made by the advance button and store the form first.
    async _capturingAdvanceRequests(callback) {
        const originalFetch = browser.fetch.bind(browser);
        browser.fetch = async (url, options = {}) => {
            try {
                this._captureAdvanceRequest(url, options);
            } catch (error) {
                console.warn("[LOCAL_BACKUP] Could not copy the advance before sending it:", error);
            }
            return originalFetch(url, options);
        };
        try {
            return await callback();
        } finally {
            browser.fetch = originalFetch;
        }
    },

    _captureAdvanceRequest(url, options) {
        const params = requestParams(options?.body);
        const action = advanceAction(url, params);
        if (!action) {
            return;
        }
        const localUuid = uuidv4();
        // The number stays on this computer. The request sent to Odoo is left
        // unchanged, so a refund is not rejected for an unknown argument.
        this.pos.recordLocalBackupEvent(action, {
            ...this._advanceSnapshot(action, params, localUuid),
            local_only: true,
        });
        this.pos._advanceBackupLocalUuid = localUuid;
        this._advanceCopyRecorded = true;
    },

    _advanceSnapshot(action, params, localUuid) {
        const partner = this._getOrderPartner?.(this._getCurrentOrder?.());
        if (action === "advance_created") {
            const lines = params.lines || [];
            const total = lines.reduce((sum, line) => sum + lineSubtotal(line), 0);
            const advanceAmount = toNumber(params.advance_amount);
            return {
                advance: {
                    local_uuid: localUuid,
                    partner_name: partner?.name || "",
                    partner_phone: partner?.phone || "",
                    amount_total: total,
                    advance_amount: advanceAmount,
                    amount_tendered: toNumber(params.amount_tendered, advanceAmount),
                    amount_remaining: Math.max(total - advanceAmount, 0),
                    payment_method_name: params.payment_method_name || "",
                },
                lines: lines.map((line) => ({
                    product_id: line.product_id || null,
                    product_name: line.product_name || line.full_product_name || "",
                    qty: toNumber(line.qty),
                    price_unit: toNumber(line.price_unit),
                    discount: toNumber(line.discount),
                    subtotal: lineSubtotal(line),
                })),
            };
        }
        if (action === "advance_completed") {
            return {
                advance: {
                    id: params.advance_order_id || null,
                    local_uuid: localUuid,
                    partner_name: partner?.name || "",
                },
                completion: {
                    amount_tendered: toNumber(params.amount_tendered),
                    remaining_paid: toNumber(params.amount_tendered),
                },
            };
        }
        const kwargs = params.kwargs || {};
        const ids = Array.isArray(params.args?.[0]) ? params.args[0] : [];
        return {
            advance: {
                id: ids[0] || null,
                local_uuid: localUuid,
                partner_name: partner?.name || "",
            },
            refund: {
                payment_method_name: kwargs.payment_method_name || "",
            },
        };
    },

    _localAdvanceUuid() {
        return this.pos._advanceBackupLocalUuid || null;
    },

    async onClickAdvanceOrder() {
        return this._runWithAdvanceBackup("create", () => super.onClickAdvanceOrder(...arguments));
    },

    async onClickCompleteAdvanceOrder() {
        return this._runWithAdvanceBackup("complete", () =>
            super.onClickCompleteAdvanceOrder(...arguments)
        );
    },

    async onClickRefundAdvanceOrder() {
        return this._runWithAdvanceBackup("refund", () =>
            super.onClickRefundAdvanceOrder(...arguments)
        );
    },

    // The receipt builders run only after the server confirmed the action.

    _buildAdvanceReceiptData({ result, payload }) {
        const data = super._buildAdvanceReceiptData(...arguments);
        try {
            this.pos.recordLocalBackupEvent("advance_created", {
                advance: {
                    id: result?.id || null,
                    local_uuid: this._localAdvanceUuid(),
                    reference: data.reference,
                    state: result?.state || "",
                    partner_name: data.customerName,
                    partner_phone: data.customerPhone,
                    amount_total: data.total,
                    advance_amount: data.advanceAmount,
                    amount_tendered: data.amountTendered,
                    change_amount: data.changeDue,
                    amount_remaining: data.remainingAmount,
                    pledge_amount: data.pledgeAmount,
                    payment_method_name: payload?.payment_method_name || "",
                },
                lines: (payload?.lines || []).map((line) => ({
                    product_id: line.product_id || null,
                    product_name: line.product_name || line.full_product_name || "",
                    qty: toNumber(line.qty),
                    price_unit: toNumber(line.price_unit),
                    discount: toNumber(line.discount),
                    subtotal: toNumber(line.qty) * toNumber(line.price_unit) * (1 - toNumber(line.discount) / 100),
                })),
                raw: { result, request: payload },
            });
        } catch (error) {
            console.warn("[LOCAL_BACKUP] Could not record the advance creation:", error);
        }
        return data;
    },

    _buildCompletionReceiptData({ result, popupPayload }) {
        const data = super._buildCompletionReceiptData(...arguments);
        try {
            this.pos.recordLocalBackupEvent("advance_completed", {
                advance: {
                    id: result?.id || popupPayload?.advance_order_id || null,
                    local_uuid: this._localAdvanceUuid(),
                    reference: data.reference,
                    state: result?.state || "",
                    partner_name: data.customerName,
                    partner_phone: data.customerPhone,
                    amount_total: data.total,
                    advance_amount: data.advanceAmount,
                    pledge_amount: data.pledgeAmount,
                },
                completion: {
                    pos_order_name: data.posOrderReference,
                    remaining_paid: data.remainingPaid,
                    amount_tendered: data.amountTendered,
                    change_amount: data.changeDue,
                    payment_method_name: data.paymentMethod,
                    advance_payment_method_name: data.advancePaymentMethod,
                    lines: receiptLines(data.lines),
                    pledge_lines: receiptLines(data.pledgeLines),
                },
                raw: { result, request: popupPayload },
            });
        } catch (error) {
            console.warn("[LOCAL_BACKUP] Could not record the advance completion:", error);
        }
        return data;
    },

    _buildRefundReceiptData({ result, popupPayload }) {
        const data = super._buildRefundReceiptData(...arguments);
        try {
            this.pos.recordLocalBackupEvent("advance_refunded", {
                advance: {
                    id: result?.id || popupPayload?.advance_order_id || null,
                    local_uuid: this._localAdvanceUuid(),
                    reference: data.reference,
                    state: result?.state || "",
                    partner_name: data.customerName,
                    partner_phone: data.customerPhone,
                    amount_total: data.total,
                    advance_amount: data.advanceAmount,
                },
                refund: {
                    amount: data.advanceAmount,
                    payment_method_name: data.paymentMethod,
                },
                raw: { result, request: popupPayload },
            });
        } catch (error) {
            console.warn("[LOCAL_BACKUP] Could not record the advance refund:", error);
        }
        return data;
    },
});
