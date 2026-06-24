/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

const PAYMENT_RELOAD_KEY = "pos_discount_cap_reload_product_once";
const FEE_PERCENTAGE = 0.04;
const FEE_MAX = 1;

function toNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
}

function toPercentFromPrices(basePrice, discountedPrice) {
    const base = toNumber(basePrice);
    const discounted = toNumber(discountedPrice);
    if (base <= 0) {
        return 0;
    }
    const percent = ((base - discounted) / base) * 100;
    return Math.max(0, Math.min(100, percent));
}

function roundPercent(value) {
    return Math.round(toNumber(value) * 100) / 100;
}

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this._restoreOrderAfterReload();
    },

    async pay() {
        if (this._consumeReloadTokenForCurrentOrder()) {
            return super.pay(...arguments);
        }
        const feesOk = await this._applyFeesForCurrentOrder();
        if (!feesOk) {
            return;
        }
        const canContinue = await this._applyDiscountCapAndConfirm();
        if (!canContinue) {
            return;
        }
        if (this._reloadBeforePaymentPage()) {
            return;
        }
        return super.pay(...arguments);
    },

    _reloadBeforePaymentPage() {
        const order = this.getOrder();
        const pricelist = order?.pricelist_id;
        if (!order || !pricelist?.cap_enabled || typeof window === "undefined") {
            return false;
        }

        try {
            window.sessionStorage.setItem(
                PAYMENT_RELOAD_KEY,
                JSON.stringify({
                    orderUuid: order.uuid,
                    at: Date.now(),
                    state: "reloaded",
                })
            );
            window.location.reload();
            return true;
        } catch {
            return false;
        }
    },

    _restoreOrderAfterReload() {
        if (typeof window === "undefined") {
            return;
        }
        const raw = window.sessionStorage.getItem(PAYMENT_RELOAD_KEY);
        if (!raw) {
            return;
        }

        let payload = null;
        try {
            payload = JSON.parse(raw);
        } catch {
            return;
        }
        if (!payload?.orderUuid || Date.now() - toNumber(payload.at) > 120000) {
            window.sessionStorage.removeItem(PAYMENT_RELOAD_KEY);
            return;
        }

        const order = this.models["pos.order"].getBy("uuid", payload.orderUuid);
        if (!order) {
            window.sessionStorage.removeItem(PAYMENT_RELOAD_KEY);
            return;
        }
        this.setOrder(order);
    },

    _consumeReloadTokenForCurrentOrder() {
        if (typeof window === "undefined") {
            return false;
        }
        const raw = window.sessionStorage.getItem(PAYMENT_RELOAD_KEY);
        if (!raw) {
            return false;
        }
        let payload = null;
        try {
            payload = JSON.parse(raw);
        } catch {
            window.sessionStorage.removeItem(PAYMENT_RELOAD_KEY);
            return false;
        }
        const order = this.getOrder();
        const isFresh = Date.now() - toNumber(payload?.at) <= 120000;
        const sameOrder = Boolean(order && payload?.orderUuid === order.uuid);
        const allowPayment = payload?.state === "reloaded";
        if (!(isFresh && sameOrder && allowPayment)) {
            return false;
        }
        window.sessionStorage.removeItem(PAYMENT_RELOAD_KEY);
        return true;
    },

    async _applyDiscountCapAndConfirm() {
        const order = this.getOrder();
        const pricelist = order?.pricelist_id;
        if (!order || !pricelist?.cap_enabled) {
            return true;
        }

        const capAmount = Math.max(0, toNumber(pricelist.cap_amount));
        const lines = order.getOrderlines().map((line, sequence) => ({
            line_uuid: line.uuid,
            sequence,
            product_id: line.product_id?.id,
            qty: line.getQuantity(),
            price_type: line.price_type,
        }));

        let evaluations;
        try {
            evaluations = await this.data.call("product.pricelist", "get_pos_cap_evaluations", [
                pricelist.id,
                lines,
            ]);
        } catch (error) {
            this.dialog.add(AlertDialog, {
                title: _t("Discount Cap Error"),
                body: _t("Could not evaluate the discount cap. Please try again."),
            });
            return false;
        }

        const byLineUuid = new Map((evaluations || []).map((item) => [item.line_uuid, item]));
        let remainingCap = capAmount;
        let consumedAmount = 0;
        let eligibleLines = 0;
        let excludedLines = 0;
        let hasChanges = false;

        for (const line of order.getOrderlines()) {
            const data = byLineUuid.get(line.uuid);
            if (!data?.cap_eligible || !data.can_apply_cap) {
                continue;
            }

            eligibleLines += 1;
            const lineBaseAmount = Math.max(0, toNumber(data.line_base_amount));
            const targetBaseUnitPrice = toNumber(data.base_unit_price);
            const targetDiscountedUnitPrice = toNumber(data.discounted_unit_price);
            let targetDiscountPercent = 0;

            if (lineBaseAmount > remainingCap + 1e-6) {
                excludedLines += 1;
                targetDiscountPercent = 0;
            } else {
                consumedAmount += lineBaseAmount;
                remainingCap = Math.max(0, remainingCap - lineBaseAmount);
                targetDiscountPercent = toPercentFromPrices(
                    targetBaseUnitPrice,
                    targetDiscountedUnitPrice
                );
            }
            targetDiscountPercent = roundPercent(targetDiscountPercent);

            if (Math.abs(toNumber(line.price_unit) - targetBaseUnitPrice) > 1e-6) {
                line.setUnitPrice(targetBaseUnitPrice);
                hasChanges = true;
            }
            if (Math.abs(toNumber(line.getDiscount()) - targetDiscountPercent) > 1e-6) {
                line.setDiscount(targetDiscountPercent);
                hasChanges = true;
            }
        }

        if (hasChanges) {
            order._markDirty?.();
        }

        const body = [
            _t("Cap Amount: %s", this.env.utils.formatCurrency(capAmount)),
            _t("Consumed Amount: %s", this.env.utils.formatCurrency(consumedAmount)),
            _t("Remaining Cap: %s", this.env.utils.formatCurrency(remainingCap)),
            _t("Eligible Lines: %s", eligibleLines),
            _t("Excluded Lines: %s", excludedLines),
        ].join("\n");

        return ask(this.env.services.dialog, {
            title: _t("Discount Cap Applied"),
            body,
            confirmLabel: _t("Continue"),
            cancelLabel: _t("Cancel"),
        });
    },
    async _applyFeesForCurrentOrder() {
        const order = this.getOrder();
        const pricelist = order?.pricelist_id;
        if (!order || !pricelist?.has_fees || order.isRefund) {
            return true;
        }

        let feeProduct = this.config?.fee_product_id;
        if (!feeProduct && this.config?.id) {
            try {
                const configData = await this.data.call("pos.config", "read", [
                    [this.config.id],
                    ["fee_product_id"],
                ]);
                const feeField = configData?.[0]?.fee_product_id;
                const feeProductId = Array.isArray(feeField) ? feeField[0] : feeField;
                if (feeProductId) {
                    feeProduct = this.models["product.product"].get(feeProductId);
                }
            } catch {
                // Keep fallback below.
            }
        }

        if (!feeProduct) {
            this.dialog.add(AlertDialog, {
                title: _t("Missing Fee Product"),
                body: _t("Please configure a Fees Product in this POS settings before payment."),
            });
            return false;
        }

        const currentLines = order.getOrderlines();
        const existingFeeLine = currentLines.find((l) => l.product_id?.id === feeProduct.id) || null;
        const linesWithoutFee = currentLines.filter((l) => l.product_id?.id !== feeProduct.id);
        // Compute from each line before discount and before tax.
        // Example: (13.8 + 16.1) * 4% = 1.196 -> capped to 1.
        const preDiscountPreTaxTotal = linesWithoutFee.reduce(
            (sum, line) => sum + Math.max(0, toNumber(line.priceExclNoDiscount)),
            0
        );
        const feeAmount = Math.min(FEE_MAX, Math.max(0, preDiscountPreTaxTotal * FEE_PERCENTAGE));
        const roundedFeeAmount = order.currency.round(feeAmount);

        if (roundedFeeAmount <= 0) {
            if (existingFeeLine) {
                order.removeOrderline(existingFeeLine);
                order._markDirty?.();
            }
            return true;
        }

        if (existingFeeLine) {
            existingFeeLine.setUnitPrice(roundedFeeAmount);
            existingFeeLine.setDiscount(0);
            existingFeeLine.setQuantity(1, true);
            existingFeeLine.price_type = "manual";
            order._markDirty?.();
            return true;
        }

        await this.addLineToOrder(
            {
                product_tmpl_id: feeProduct.product_tmpl_id,
                product_id: feeProduct,
                qty: 1,
                price_unit: roundedFeeAmount,
            },
            order,
            {},
            false
        );
        const addedFeeLine = order
            .getOrderlines()
            .find((line) => line.product_id?.id === feeProduct.id && line.price_type === "manual");
        if (addedFeeLine) {
            addedFeeLine.setDiscount(0);
            addedFeeLine.setQuantity(1, true);
            addedFeeLine.price_type = "manual";
        }
        order._markDirty?.();
        return true;
    },
});
