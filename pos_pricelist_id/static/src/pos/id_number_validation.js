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

function describePricelistValue(value) {
    if (!value) {
        return null;
    }
    if (Array.isArray(value)) {
        return {
            type: "array",
            raw: value,
            id: value[0] || null,
            label: value[1] || null,
        };
    }
    if (typeof value === "object") {
        return {
            type: "object",
            id: value.id || null,
            name: value.name || value.display_name || null,
            required_id_number:
                value.required_id_number !== undefined ? Boolean(value.required_id_number) : "missing",
        };
    }
    return {
        type: typeof value,
        value,
    };
}

function logJson(label, payload) {
    try {
        console.log(`${label} ${JSON.stringify(payload)}`);
    } catch {
        console.log(label, payload);
    }
}

function getActivePricelistValue(order, pos) {
    if (order?.pricelist_id) {
        return order.pricelist_id;
    }
    if (order?.raw?.pricelist_id) {
        return order.raw.pricelist_id;
    }
    if (pos?.getOrder?.()?.pricelist_id) {
        return pos.getOrder().pricelist_id;
    }
    return pos?.config?.pricelist_id || null;
}

function resolvePricelist(order, pos) {
    const pricelistValue = getActivePricelistValue(order, pos);

    const pricelistId = extractPricelistId(pricelistValue);
    logJson("[POS_PRICELIST_ID] resolvePricelist input details", {
        orderPricelistRaw: describePricelistValue(order?.raw?.pricelist_id),
        orderPricelist: describePricelistValue(order?.pricelist_id),
        posCurrentOrderPricelist: describePricelistValue(pos?.getOrder?.()?.pricelist_id),
        configPricelist: describePricelistValue(pos?.config?.pricelist_id),
        selectedPricelist: describePricelistValue(pricelistValue),
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

    logJson("[POS_PRICELIST_ID] resolvePricelist output details", {
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
        const pricelistId = extractPricelistId(getActivePricelistValue(this.order, this.pos));

        let requiredFromServer = false;
        if (pricelistId) {
            try {
                const rows = await this.pos.data.call("product.pricelist", "read", [
                    [pricelistId],
                    ["required_id_number"],
                ]);
                requiredFromServer = Boolean(rows?.[0]?.required_id_number);
                logJson("[POS_PRICELIST_ID] Server read result", {
                    pricelistId,
                    rows,
                    requiredFromServer,
                });
            } catch (error) {
                console.warn("[POS_PRICELIST_ID] Failed to read required_id_number from server", {
                    pricelistId,
                    error,
                });
            }
        }

        const isRequired = Boolean(pricelist?.required_id_number || requiredFromServer);
        logJson("[POS_PRICELIST_ID] Required check details", {
            pricelistId,
            pricelistName: pricelist?.name || pricelist?.display_name || null,
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

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        data.customer_id_number = this.customer_id_number || false;
        return data;
    },

    updatePricelistAndFiscalPosition(newPartner) {
        // Some POS custom modules may call this during record setup, before lines are initialized.
        // In that phase, super.updatePricelistAndFiscalPosition() triggers setPricelist(), which
        // recomputes prices and expects this.lines.map(...) to exist.
        if (!this.lines || typeof this.lines.map !== "function") {
            console.log(
                "[POS_PRICELIST_ID] Skipping updatePricelistAndFiscalPosition during setup; lines not ready"
            );
            return;
        }

        const lockedPricelist = this.pricelist_id || this.config?.pricelist_id || false;
        super.updatePricelistAndFiscalPosition(newPartner);

        if (!lockedPricelist) {
            return;
        }

        if (extractPricelistId(this.pricelist_id) !== extractPricelistId(lockedPricelist)) {
            this.setPricelist(lockedPricelist);
            logJson("[POS_PRICELIST_ID] Restored session/order pricelist after partner change", {
                partnerId: newPartner?.id || null,
                lockedPricelist: describePricelistValue(lockedPricelist),
                currentPricelist: describePricelistValue(this.pricelist_id),
            });
        }
    },
});
