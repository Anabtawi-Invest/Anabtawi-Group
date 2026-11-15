/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { uuidv4 } from "@point_of_sale/utils";
import { rpc, ConnectionLostError } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { CompleteAdvanceOrderPopup } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/complete_advance_order_popup";
import { RefundAdvanceOrderPopup } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/refund_advance_order_popup";
import { captureDangerNotifications } from "@pos_local_sql_backup/app/pos_store_patch";
import { expandAdvanceLinesWithPledges } from "@pos_local_sql_backup_advance/app/local_advance_store";

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

// Odoo 19 sends these calls with XMLHttpRequest, not fetch. The RPC bus
// fires as soon as the request is built, so the form can be copied even when
// the connection is already down.
function advanceAction(url, params) {
    const path = typeof url === "string" ? url : "";
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
                } else if (
                    failedAction === "create" &&
                    this._advanceCopyRecorded &&
                    errors.length
                ) {
                    // The form was copied locally. Clear the cart like a normal create.
                    const currentOrder = this._getCurrentOrder?.();
                    if (currentOrder) {
                        this.pos.removeOrder(currentOrder);
                    }
                    this.pos.addNewOrder?.();
                    this.notification.add(
                        _t(
                            "Advance saved on this register. It will sync when the connection is back."
                        ),
                        { type: "warning" }
                    );
                }
                return result;
            });
        } finally {
            this.pos._advanceBackupLocalUuid = null;
        }
    },

    // Watch the Odoo call made by the advance button and store the form first.
    // rpc._rpc is patched so local_uuid is sent to Odoo for later idempotent sync.
    async _capturingAdvanceRequests(callback) {
        const originalRpc = rpc._rpc;
        const self = this;
        rpc._rpc = function (url, params = {}, settings = {}) {
            const action = advanceAction(url, params);
            if (action) {
                try {
                    params = self._prepareAdvanceRpcParams(action, params);
                    self._captureAdvanceRequest(url, params);
                } catch (error) {
                    console.warn(
                        "[LOCAL_BACKUP] Could not copy the advance before sending it:",
                        error
                    );
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

    _prepareAdvanceRpcParams(action, params) {
        const next = { ...params };
        if (action === "advance_created") {
            next.local_uuid = next.local_uuid || uuidv4();
        } else if (action === "advance_completed") {
            next.local_uuid = next.local_uuid || uuidv4();
        } else if (action === "advance_refunded") {
            next.kwargs = { ...(next.kwargs || {}) };
            // Refund keeps the request unchanged for the server signature.
        }
        return next;
    },

    _captureAdvanceRequest(url, params) {
        const action = advanceAction(url, params);
        if (!action) {
            return;
        }
        const localUuid =
            params.local_uuid ||
            params.kwargs?.local_uuid ||
            uuidv4();
        if (action === "advance_created") {
            const partner = this._getOrderPartner?.(this._getCurrentOrder?.());
            this.pos.saveLocalAdvanceFromCreate(params, localUuid, {
                partner_name: partner?.name || "",
                partner_phone: partner?.phone || "",
                state: "waiting",
                pending_action: "create",
            });
        }
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
            const { lines, pledge_amount } = expandAdvanceLinesWithPledges(
                this.pos,
                params.lines || [],
                Boolean(params.site_service)
            );
            const total = lines.reduce(
                (sum, line) => sum + toNumber(line.subtotal, lineSubtotal(line)),
                0
            );
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
                    pledge_amount,
                    payment_method_name: params.payment_method_name || "",
                },
                lines: lines.map((line) => ({
                    product_id: line.product_id || null,
                    product_name: line.product_name || line.full_product_name || "",
                    qty: toNumber(line.qty),
                    price_unit: toNumber(line.price_unit),
                    discount: toNumber(line.discount),
                    subtotal: toNumber(line.subtotal, lineSubtotal(line)),
                    is_pledge_line: Boolean(
                        line.is_pledge_line || line.is_site_service_pledge_line
                    ),
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
        return this._runWithAdvanceBackup("complete", async () => {
            const popupPayload = await makeAwaitable(this.dialog, CompleteAdvanceOrderPopup, {
                posConfigId: this.pos.config.id,
                pos: this.pos,
            });
            if (!popupPayload) {
                return;
            }
            if (
                popupPayload.is_local ||
                popupPayload.from_server_cache ||
                (popupPayload.local_uuid && !(popupPayload.advance_order_id > 0))
            ) {
                this.pos.completeLocalAdvance(popupPayload);
                this._advanceCopyRecorded = true;
                this.notification.add(
                    _t(
                        "Advance completion saved on this register. It will sync when the connection is back."
                    ),
                    { type: "warning" }
                );
                return;
            }
            try {
                const result = await rpc("/pos/complete_advance_order", {
                    advance_order_id: popupPayload.advance_order_id,
                    pos_config_id: this.pos.config.id,
                    payment_method_id: popupPayload.payment_method_id,
                    amount_tendered: popupPayload.amount_tendered,
                });
                this.notification.add(_t("Advance order completed successfully."), {
                    type: "success",
                });
                this.pos.refreshCompletableAdvanceCache?.();
                try {
                    const receiptPayload =
                        result && typeof result === "object" && result.name ? result : null;
                    if (receiptPayload) {
                        const printResult = await this._printAdvanceReceipt(
                            this._buildCompletionReceiptData({
                                result: receiptPayload,
                                popupPayload,
                            })
                        );
                        if (!printResult?.printed) {
                            this.notification.add(
                                _t("Advance order completed but receipt printing failed."),
                                { type: "warning" }
                            );
                        }
                    }
                } catch (printError) {
                    const printMessage =
                        printError?.message === "POPUP_BLOCKED"
                            ? _t("Please allow pop-ups to print the completion receipt.")
                            : printError?.body ||
                              printError?.message ||
                              _t("Advance order completed but receipt printing failed.");
                    this.notification.add(printMessage, { type: "warning" });
                }
            } catch (error) {
                if (error instanceof ConnectionLostError) {
                    this.pos.completeLocalAdvance(popupPayload);
                    this._advanceCopyRecorded = true;
                    this.notification.add(
                        _t(
                            "Advance completion saved on this register. It will sync when the connection is back."
                        ),
                        { type: "warning" }
                    );
                    return;
                }
                const msg =
                    error?.data?.message ||
                    error?.message ||
                    _t("Failed to complete advance order.");
                this.notification.add(msg, { type: "danger" });
            }
        });
    },

    async onClickRefundAdvanceOrder() {
        return this._runWithAdvanceBackup("refund", async () => {
            const popupPayload = await makeAwaitable(this.dialog, RefundAdvanceOrderPopup, {
                posConfigId: this.pos.config.id,
                pos: this.pos,
            });
            if (!popupPayload?.advance_order_id) {
                return;
            }
            if (
                popupPayload.is_local ||
                popupPayload.from_server_cache ||
                (popupPayload.local_uuid && !(popupPayload.advance_order_id > 0))
            ) {
                this.pos.refundLocalAdvance(popupPayload);
                this._advanceCopyRecorded = true;
                this.notification.add(
                    _t(
                        "Advance refund saved on this register. It will sync when the connection is back."
                    ),
                    { type: "warning" }
                );
                return;
            }
            try {
                const result = await this.orm.call(
                    "pos.advance.order",
                    "action_refund_advance_payment",
                    [[popupPayload.advance_order_id]],
                    {
                        pos_config_id: this.pos.config.id,
                        pos_payment_method_id: popupPayload.payment_method_id,
                        refund_pos_session_id: this.pos.session?.id,
                    }
                );
                this.notification.add(
                    _t("Advance refunded: %s", result?.name || popupPayload.reference || ""),
                    { type: "success" }
                );
                this.pos.refreshRefundableAdvanceCache?.();
                this.pos.refreshCompletableAdvanceCache?.();
                this.pos.refreshActivePledgeCache?.();
                try {
                    const printResult = await this._printAdvanceReceipt(
                        this._buildRefundReceiptData({ result, popupPayload })
                    );
                    if (!printResult?.printed) {
                        this.notification.add(_t("Advance refunded but receipt printing failed."), {
                            type: "warning",
                        });
                    }
                } catch (printError) {
                    const printMessage =
                        printError?.message === "POPUP_BLOCKED"
                            ? _t("Please allow pop-ups to print the refund receipt.")
                            : printError?.body ||
                              printError?.message ||
                              _t("Advance refunded but receipt printing failed.");
                    this.notification.add(printMessage, { type: "warning" });
                }
            } catch (error) {
                if (error instanceof ConnectionLostError) {
                    this.pos.refundLocalAdvance(popupPayload);
                    this._advanceCopyRecorded = true;
                    this.notification.add(
                        _t(
                            "Advance refund saved on this register. It will sync when the connection is back."
                        ),
                        { type: "warning" }
                    );
                    return;
                }
                const msg =
                    error?.data?.message ||
                    error?.message ||
                    _t("Failed to refund advance order.");
                this.notification.add(msg, { type: "danger" });
            }
        });
    },

    // The receipt builders run only after the server confirmed the action.

    _buildAdvanceReceiptData({ result, payload }) {
        const data = super._buildAdvanceReceiptData(...arguments);
        try {
            const localUuid = this._localAdvanceUuid();
            if (localUuid) {
                this.pos.markLocalAdvanceCreated(localUuid, result || {});
            }
            this.pos.recordLocalBackupEvent("advance_created", {
                advance: {
                    id: result?.id || null,
                    local_uuid: localUuid,
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
