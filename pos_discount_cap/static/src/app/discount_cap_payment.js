/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import {
    applyCapLineUpdates,
    computeSequentialCapDiscounts,
    toNumber,
} from "@pos_discount_cap/app/discount_cap_utils";

const PAYMENT_RELOAD_KEY = "pos_discount_cap_reload_product_once";
const FEE_PERCENTAGE = 0.04;
const FEE_MAX = 1;

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this._restoreOrderAfterReload();
    },

    async pay() {
        const feesOk = await this._applyFeesForCurrentOrder();
        if (!feesOk) {
            return;
        }
        const canContinue = await this._applyDiscountCapAndConfirm();
        if (!canContinue) {
            return;
        }
        return super.pay(...arguments);
    },

    _reapplyCapLines(order, capLines, promotionalDiscountAmount) {
        applyCapLineUpdates(
            order,
            new Map(
                (capLines || []).map((line) => [
                    line.line_uuid,
                    {
                        targetBaseUnitPrice: toNumber(line.price_unit),
                        targetDiscountPercent: toNumber(line.discount),
                    },
                ])
            )
        );
        if (promotionalDiscountAmount != null) {
            order.promotional_discount_amount = toNumber(promotionalDiscountAmount);
        }
    },

    async _reloadBeforePaymentPage(order) {
        if (!order || typeof window === "undefined") {
            return false;
        }

        const capLines = order.getOrderlines().map((line) => ({
            line_uuid: line.uuid,
            product_id: line.product_id?.id,
            price_unit: toNumber(line.price_unit),
            discount: toNumber(line.getDiscount()),
            qty: line.getQuantity(),
        }));

        order._markDirty?.();

        try {
            await this.data.synchronizeLocalDataInIndexedDB();
            window.sessionStorage.setItem(
                PAYMENT_RELOAD_KEY,
                JSON.stringify({
                    orderUuid: order.uuid,
                    at: Date.now(),
                    state: "reloaded",
                    lines: capLines,
                    promotional_discount_amount: toNumber(order.promotional_discount_amount),
                })
            );
            const url = new URL(window.location.href);
            url.searchParams.set("limited_loading", "0");
            window.location.href = url.href;
            return true;
        } catch (error) {
            console.error("[pos_discount_cap] Reload before payment failed", {
                orderUuid: order.uuid,
                capLines,
                error,
            });
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
            window.sessionStorage.removeItem(PAYMENT_RELOAD_KEY);
            return;
        }
        if (!payload?.orderUuid || Date.now() - toNumber(payload.at) > 120000) {
            window.sessionStorage.removeItem(PAYMENT_RELOAD_KEY);
            return;
        }
        if (payload.state !== "reloaded") {
            return;
        }

        const order = this.models["pos.order"].getBy("uuid", payload.orderUuid);
        if (!order) {
            console.warn("[pos_discount_cap] Order not found after reload", {
                orderUuid: payload.orderUuid,
                lines: payload.lines,
            });
            return;
        }

        this._reapplyCapLines(order, payload.lines, payload.promotional_discount_amount);
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
        if (payload.promotional_discount_amount != null) {
            order.promotional_discount_amount = toNumber(payload.promotional_discount_amount);
        }
        return true;
    },

    async _resolveCapPricelistSettings(pricelist) {
        if (!pricelist?.id) {
            return null;
        }
        if (pricelist.cap_enabled !== undefined) {
            return pricelist;
        }
        try {
            const rows = await this.data.call("product.pricelist", "read", [
                [pricelist.id],
                ["cap_enabled", "cap_amount", "has_fees"],
            ]);
            return rows?.[0] ? { ...pricelist, ...rows[0] } : pricelist;
        } catch {
            return pricelist;
        }
    },

    async _applyDiscountCapAndConfirm() {
        const order = this.getOrder();
        const pricelist = await this._resolveCapPricelistSettings(order?.pricelist_id);
        if (!order || !pricelist?.cap_enabled) {
            order.promotional_discount_amount = 0;
            return true;
        }

        const capAmount = Math.max(0, toNumber(pricelist.cap_amount));
        const pricelistId = pricelist.id || order.pricelist_id?.id;
        const lines = order.getOrderlines().map((line, sequence) => ({
            line_uuid: line.uuid,
            sequence,
            product_id: line.product_id?.id || line.getProduct?.()?.id,
            qty: line.getQuantity(),
            price_type: line.price_type || "original",
            price_unit: toNumber(line.price_unit),
        }));

        console.info("[pos_discount_cap] Payment cap check started", {
            orderUuid: order.uuid,
            pricelistId,
            pricelistName: pricelist.name || pricelist.display_name,
            capEnabled: pricelist.cap_enabled,
            capAmount,
            orderPricelistId: order.pricelist_id?.id,
            orderPricelistName: order.pricelist_id?.name || order.pricelist_id?.display_name,
            lineCount: lines.length,
            lines,
        });

        let evaluations;
        try {
            evaluations = await this.data.call("product.pricelist", "get_pos_cap_evaluations", [
                pricelistId,
                lines,
            ]);
            console.info("[pos_discount_cap] Server evaluations", evaluations);
        } catch (error) {
            console.error("[pos_discount_cap] Discount cap evaluation failed", {
                pricelistId,
                capAmount,
                lineCount: lines.length,
                lines,
                error,
            });
            this.dialog.add(AlertDialog, {
                title: _t("Discount Cap Error"),
                body: _t("Could not evaluate the discount cap. Please try again."),
            });
            return false;
        }

        const capResult = computeSequentialCapDiscounts({
            order,
            evaluations,
            capAmount,
        });
        console.info("[pos_discount_cap] Cap computation result", capResult);
        if (capResult.skippedLines?.length) {
            console.warn("[pos_discount_cap] Skipped lines", capResult.skippedLines);
        }
        applyCapLineUpdates(order, capResult.lineUpdates);
        order.promotional_discount_amount = capResult.consumedAmount;

        const bodyLines = [
            _t("Cap Amount: %s", this.env.utils.formatCurrency(capAmount)),
            _t("Applied Discount: %s", this.env.utils.formatCurrency(capResult.consumedAmount)),
            _t("Remaining Cap: %s", this.env.utils.formatCurrency(capResult.remainingCap)),
            _t("Eligible Lines: %s", capResult.eligibleLines),
            _t("Adjusted Lines: %s", capResult.adjustedLines),
            _t("Lines After Cap: %s", capResult.excludedAfterCapLines),
        ];
        if (capResult.eligibleLines === 0 && capResult.skippedLines?.length) {
            bodyLines.push("");
            bodyLines.push(_t("Debug - skipped lines:"));
            for (const skipped of capResult.skippedLines) {
                bodyLines.push(
                    `- ${skipped.product || skipped.line_uuid}: ${skipped.reason}`
                );
            }
        }
        const body = bodyLines.join("\n");

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
