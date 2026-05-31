/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { MepIdPopup } from "./mep_id_popup";

function normalizeRelationalValue(value) {
    if (typeof value === "number") {
        return value;
    }
    if (Array.isArray(value)) {
        return value[0] || null;
    }
    if (value && typeof value === "object") {
        return value.id || null;
    }
    return null;
}

function getRequiredMepPaymentMethodIds(pos) {
    const ids = new Set();
    for (const value of pos?.config?.mep_payment_method_ids || []) {
        const id = normalizeRelationalValue(value);
        if (id) {
            ids.add(id);
        }
    }
    return ids;
}

function requiresMepId(pos, paymentMethod) {
    return getRequiredMepPaymentMethodIds(pos).has(paymentMethod?.id);
}

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        const added = await super.addNewPaymentLine(paymentMethod);
        if (!added || !requiresMepId(this.pos, paymentMethod)) {
            return added;
        }

        const paymentLine = this.currentOrder.getSelectedPaymentline() || this.paymentLines.at(-1);
        if (!paymentLine) {
            return added;
        }

        const mepId = await makeAwaitable(this.dialog, MepIdPopup, {
            title: _t("Enter MEP ID"),
            placeholder: _t("Type MEP ID"),
        });
        const normalizedMepId = (mepId || "").trim();

        if (!normalizedMepId) {
            this.currentOrder.removePaymentline(paymentLine);
            this.numberBuffer.reset();
            return false;
        }

        paymentLine.mep_id = normalizedMepId;
        paymentLine._markDirty?.();
        return true;
    },
});

patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation() {
        const ok = await super.askBeforeValidation();
        if (ok === false) {
            return false;
        }

        const requiredMethodIds = getRequiredMepPaymentMethodIds(this.pos);
        if (!requiredMethodIds.size) {
            this.order.mep_id = false;
            this.order._markDirty?.();
            return true;
        }

        let collectedMepId = "";
        for (const paymentLine of this.order.payment_ids || []) {
            if (!requiredMethodIds.has(paymentLine.payment_method_id?.id)) {
                continue;
            }
            const lineMepId = (paymentLine.mep_id || "").trim();
            if (!lineMepId) {
                this.pos.dialog.add(AlertDialog, {
                    title: _t("Missing MEP ID"),
                    body: _t("Please enter a MEP ID for all selected MEP payment methods."),
                });
                return false;
            }
            if (!collectedMepId) {
                collectedMepId = lineMepId;
            }
        }

        this.order.mep_id = collectedMepId || false;
        this.order._markDirty?.();
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
