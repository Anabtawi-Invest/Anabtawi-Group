/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
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
        const { result, errors } = await captureDangerNotifications(this, callback);
        if (errors.length) {
            const partner = this._getOrderPartner?.(this._getCurrentOrder?.());
            this.pos.recordLocalBackupEvent("advance_failed", {
                failed_action: failedAction,
                error: errors.join(" | "),
                advance: failedAction === "create" ? { partner_name: partner?.name || "" } : {},
            });
        }
        return result;
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
