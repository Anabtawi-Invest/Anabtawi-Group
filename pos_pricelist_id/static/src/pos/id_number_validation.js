/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

console.log("[POS_PRICELIST_ID] id_number_validation.js loaded");

function extractPricelistId(value) {
    if (!value) {
        return null;
    }
    if (Array.isArray(value)) {
        return value[0] || null;
    }
    if (typeof value === "object") {
        return value.id || null;
    }
    return value;
}

function resolvePricelist(order, pos) {
    const pricelistValue =
        (typeof order?.get_pricelist === "function" && order.get_pricelist()) ||
        order?.pricelist_id ||
        order?.raw?.pricelist_id ||
        pos?.config?.pricelist_id;

    const pricelistId = extractPricelistId(pricelistValue);
    console.log("[POS_PRICELIST_ID] resolvePricelist input", {
        hasGetPricelist: typeof order?.get_pricelist === "function",
        orderPricelistRaw: order?.raw?.pricelist_id,
        orderPricelist: order?.pricelist_id,
        configPricelist: pos?.config?.pricelist_id,
        resolvedPricelistId: pricelistId,
    });
    if (!pricelistId) {
        console.warn("[POS_PRICELIST_ID] No pricelistId resolved");
        return null;
    }

    const resolved =
        (pricelistValue && typeof pricelistValue === "object" && pricelistValue.required_id_number !== undefined
            ? pricelistValue
            : null) ||
        pos.models["product.pricelist"]?.get(pricelistId) ||
        pos.models["product.pricelist"]?.find((p) => p.id === pricelistId) ||
        null;

    console.log("[POS_PRICELIST_ID] resolvePricelist output", {
        id: resolved?.id,
        name: resolved?.name || resolved?.display_name,
        required_id_number: resolved?.required_id_number,
    });
    return resolved;
}

patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation() {
        console.log("[POS_PRICELIST_ID] askBeforeValidation start", {
            orderUuid: this.order?.uuid,
            orderName: this.order?.name,
        });
        const ok = await super.askBeforeValidation();
        console.log("[POS_PRICELIST_ID] super.askBeforeValidation result", ok);
        if (ok === false) {
            console.warn("[POS_PRICELIST_ID] Blocked by previous validation patch");
            return false;
        }

        const pricelist = resolvePricelist(this.order, this.pos);
        const pricelistId = extractPricelistId(
            (typeof this.order?.get_pricelist === "function" && this.order.get_pricelist()) ||
                this.order?.pricelist_id ||
                this.order?.raw?.pricelist_id ||
                this.pos?.config?.pricelist_id
        );

        let requiredFromServer = false;
        if (pricelistId) {
            try {
                const rows = await this.pos.data.call("product.pricelist", "read", [
                    [pricelistId],
                    ["required_id_number"],
                ]);
                requiredFromServer = Boolean(rows?.[0]?.required_id_number);
            } catch (error) {
                console.warn("[POS_PRICELIST_ID] Failed to read required_id_number from server", {
                    pricelistId,
                    error,
                });
            }
        }

        const isRequired = Boolean(pricelist?.required_id_number || requiredFromServer);
        console.log("[POS_PRICELIST_ID] Required check", {
            pricelistId,
            requiredFromModel: pricelist?.required_id_number,
            requiredFromServer,
            isRequired,
        });
        if (!isRequired) {
            console.log("[POS_PRICELIST_ID] Skipping popup: required_id_number is false");
            return true;
        }

        console.log("[POS_PRICELIST_ID] Showing ID number popup");
        const idNumber = await makeAwaitable(this.pos.dialog, TextInputPopup, {
            title: _t("Customer ID Number"),
            placeholder: _t("Enter customer ID number"),
            startingValue: "",
        });
        console.log("[POS_PRICELIST_ID] Popup payload", { idNumber });

        const value = (idNumber || "").trim();
        if (!value) {
            console.warn("[POS_PRICELIST_ID] Empty ID number entered, blocking validation");
            this.pos.dialog.add(AlertDialog, {
                title: _t("Missing ID Number"),
                body: _t("This pricelist requires entering the customer's ID number before validation."),
            });
            return false;
        }

        // Keep value in the current POS order so it can be shown on the receipt.
        this.order.customer_id_number = value;
        this.order._markDirty?.();
        console.log("[POS_PRICELIST_ID] ID number entered, allowing validation");
        return true;
    },
});

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        // Preserve the value entered in POS even if the order is updated from backend data.
        this.customer_id_number = vals?.customer_id_number || this.customer_id_number || "";
        console.log("[POS_PRICELIST_ID] PosOrder.setup customer_id_number", this.customer_id_number);
    },
});
