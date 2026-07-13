/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

/**
 * Per-aggregator order ID capture at POS payment.
 *
 * Reads its config from online.campaign.aggregator (module online_campaigns_discount):
 * each aggregator's payment_method_ids says which POS payment method it maps to,
 * require_order_ref/order_ref_digit_length say whether and how many digits to demand.
 * Adding a new aggregator (Careem, MyThings, ...) needs no code change here - this
 * loops over whatever aggregators are configured.
 */

function normalizeRelationId(value) {
    if (value === null || value === undefined) {
        return null;
    }
    if (typeof value === "number") {
        return value;
    }
    if (Array.isArray(value)) {
        return value.length ? normalizeRelationId(value[0]) : null;
    }
    if (typeof value === "object") {
        return value.id ?? null;
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

function findAggregatorForPaymentMethod(pos, paymentMethod) {
    const methodId = normalizeRelationId(paymentMethod);
    if (!methodId) {
        return null;
    }
    const aggregators = toIterable(pos.models["online.campaign.aggregator"]?.getAll?.());
    for (const aggregator of aggregators) {
        if (!aggregator.require_order_ref) {
            continue;
        }
        const linkedMethodIds = toIterable(aggregator.payment_method_ids).map(normalizeRelationId);
        if (linkedMethodIds.includes(methodId)) {
            return aggregator;
        }
    }
    return null;
}

function findRequiredAggregatorOnOrder(pos, order) {
    for (const paymentLine of order.payment_ids || []) {
        const aggregator = findAggregatorForPaymentMethod(pos, paymentLine.payment_method_id);
        if (aggregator) {
            return aggregator;
        }
    }
    return null;
}

async function promptForOrderRef(pos, aggregator, startingValue = "") {
    const digitLength = aggregator.order_ref_digit_length || 10;
    const pattern = new RegExp(`^\\d{${digitLength}}$`);
    if (pattern.test((startingValue || "").trim())) {
        return startingValue.trim();
    }
    const entered = await makeAwaitable(pos.dialog, TextInputPopup, {
        title: `${aggregator.name} Order ID`,
        placeholder: `Enter the ${digitLength}-digit ${aggregator.name} order number`,
        startingValue: startingValue || "",
    });
    const value = (entered || "").trim();
    if (!pattern.test(value)) {
        pos.dialog.add(AlertDialog, {
            title: _t("Invalid Order ID"),
            body: `${aggregator.name} order number must be exactly ${digitLength} digits.`,
        });
        return null;
    }
    return value;
}

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        const added = await super.addNewPaymentLine(paymentMethod);
        if (!added) {
            return added;
        }

        const aggregator = findAggregatorForPaymentMethod(this.pos, paymentMethod);
        if (!aggregator) {
            return added;
        }

        const order = this.currentOrder;
        const value = await promptForOrderRef(this.pos, aggregator, order.online_aggregator_order_ref);
        if (!value) {
            const paymentLine = order.getSelectedPaymentline() || this.paymentLines?.at(-1);
            if (paymentLine) {
                order.removePaymentline(paymentLine);
            }
            this.numberBuffer.reset();
            return false;
        }

        order.update({ online_aggregator_order_ref: value });
        return true;
    },
});

patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation() {
        const ok = await super.askBeforeValidation();
        if (ok === false) {
            return false;
        }

        const order = this.order;
        const aggregator = findRequiredAggregatorOnOrder(this.pos, order);
        if (!aggregator) {
            return true;
        }

        const value = await promptForOrderRef(this.pos, aggregator, order.online_aggregator_order_ref);
        if (!value) {
            return false;
        }

        order.update({ online_aggregator_order_ref: value });
        return true;
    },
});
