/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { MepIdPopup } from "./mep_id_popup";

console.log("[POS_MEP_ID] payment_mep_id_patch loaded");

function normalizeRelationalValue(value) {
    if (value === null || value === undefined) {
        return null;
    }
    if (typeof value === "number") {
        return value;
    }
    if (typeof value === "string") {
        const numValue = Number(value);
        return Number.isFinite(numValue) ? numValue : null;
    }
    if (Array.isArray(value)) {
        if (value.length && typeof value[0] === "number") {
            return value[0] || null;
        }
        for (const nestedValue of value) {
            const nestedId = normalizeRelationalValue(nestedValue);
            if (nestedId) {
                return nestedId;
            }
        }
        return null;
    }
    if (value && typeof value === "object") {
        if (value.id) {
            return value.id;
        }
        if (value.resId) {
            return value.resId;
        }
        if (value.raw?.id) {
            return value.raw.id;
        }
        if (value.record?.id) {
            return value.record.id;
        }
        return null;
    }
    return null;
}

function toIterable(value) {
    if (!value) {
        return [];
    }
    if (Array.isArray(value)) {
        return value;
    }
    if (typeof value.getAll === "function") {
        return value.getAll();
    }
    if (Array.isArray(value.records)) {
        return value.records;
    }
    return [value];
}

function getRequiredMepPaymentMethodIds(pos) {
    const rawValues = pos?.config?.mep_payment_method_ids;
    const ids = new Set();
    for (const value of toIterable(rawValues)) {
        const id = normalizeRelationalValue(value);
        if (id) {
            ids.add(id);
        }
    }
    console.log("[POS_MEP_ID] Resolved MEP payment method IDs", {
        configId: pos?.config?.id,
        rawValues,
        resolvedIds: [...ids],
    });
    return ids;
}

function requiresMepId(pos, paymentMethod) {
    const requiredIds = getRequiredMepPaymentMethodIds(pos);
    const methodId = normalizeRelationalValue(paymentMethod);
    const required = requiredIds.has(methodId);
    console.log("[POS_MEP_ID] requiresMepId check", {
        methodId,
        methodName: paymentMethod?.name,
        required,
    });
    return required;
}

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        console.log("[POS_MEP_ID] addNewPaymentLine start", {
            methodId: paymentMethod?.id,
            methodName: paymentMethod?.name,
        });
        const added = await super.addNewPaymentLine(paymentMethod);
        if (!added || !requiresMepId(this.pos, paymentMethod)) {
            console.log("[POS_MEP_ID] Popup skipped", {
                added,
                methodId: paymentMethod?.id,
            });
            return added;
        }

        const paymentLine = this.currentOrder.getSelectedPaymentline() || this.paymentLines.at(-1);
        if (!paymentLine) {
            console.warn("[POS_MEP_ID] No payment line found after add");
            return added;
        }

        console.log("[POS_MEP_ID] Opening MEP ID popup", {
            orderUuid: this.currentOrder?.uuid,
            paymentLineUuid: paymentLine?.uuid,
            methodId: paymentLine?.payment_method_id?.id,
        });
        const mepId = await makeAwaitable(this.dialog, MepIdPopup, {
            title: _t("Enter MEPs ID"),
            placeholder: _t("Type MEP ID"),
        });
        const normalizedMepId = (mepId || "").trim();
        console.log("[POS_MEP_ID] Popup result", {
            mepId,
            normalizedMepId,
        });

        if (!normalizedMepId) {
            this.currentOrder.removePaymentline(paymentLine);
            this.numberBuffer.reset();
            console.warn("[POS_MEP_ID] Empty MEP ID, payment line removed", {
                paymentLineUuid: paymentLine?.uuid,
            });
            return false;
        }

        paymentLine.mep_id = normalizedMepId;
        paymentLine._markDirty?.();
        console.log("[POS_MEP_ID] MEP ID stored on payment line", {
            paymentLineUuid: paymentLine?.uuid,
            mepId: normalizedMepId,
        });
        return true;
    },
});

patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation() {
        const ok = await super.askBeforeValidation();
        if (ok === false) {
            console.warn("[POS_MEP_ID] Validation stopped by previous check");
            return false;
        }

        const requiredMethodIds = getRequiredMepPaymentMethodIds(this.pos);
        if (!requiredMethodIds.size) {
            this.order.mep_id = false;
            this.order._markDirty?.();
            console.log("[POS_MEP_ID] No MEP-restricted methods configured");
            return true;
        }

        let collectedMepId = "";
        for (const paymentLine of this.order.payment_ids || []) {
            if (!requiredMethodIds.has(paymentLine.payment_method_id?.id)) {
                continue;
            }
            const lineMepId = (paymentLine.mep_id || "").trim();
            console.log("[POS_MEP_ID] Checking payment line for MEP ID", {
                paymentLineUuid: paymentLine?.uuid,
                methodId: paymentLine?.payment_method_id?.id,
                mepId: lineMepId,
            });
            if (!lineMepId) {
                this.pos.dialog.add(AlertDialog, {
                    title: _t("Missing MEP ID"),
                    body: _t("Please enter a MEPs ID for all selected MEP payment methods."),
                });
                console.warn("[POS_MEP_ID] Missing MEP ID on required payment line");
                return false;
            }
            if (!collectedMepId) {
                collectedMepId = lineMepId;
            }
        }

        this.order.mep_id = collectedMepId || false;
        this.order._markDirty?.();
        console.log("[POS_MEP_ID] Order MEP ID prepared for sync", {
            orderUuid: this.order?.uuid,
            mepId: this.order.mep_id,
        });
        return true;
    },
});

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        this.mep_id = vals?.mep_id || this.mep_id || false;
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        data.mep_id = this.mep_id || false;
        return data;
    },
});
