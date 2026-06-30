/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import {
    applyCapDiscountUpdates,
    buildCapConfirmationBody,
    computeCapDiscountUpdates,
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
        const order = this.getOrder();
        const pricelist = order?.pricelist_id;
        if (order && pricelist?.cap_enabled) {
            if (await this._reloadBeforePaymentPage(order)) {
                return;
            }
        }
        return super.pay(...arguments);
    },

    _reapplyCapLines(order, capPayload) {
        const lineData = Array.isArray(capPayload) ? capPayload : capPayload?.lines || [];
        const promotionalAmount = Array.isArray(capPayload)
            ? 0
            : toNumber(capPayload?.promotional_discount_amount);
        const byLineUuid = new Map(lineData.map((line) => [line.line_uuid, line]));
        let hasChanges = false;

        for (const line of order.getOrderlines()) {
            const data = byLineUuid.get(line.uuid);
            if (!data) {
                continue;
            }
            const targetUnitPrice = toNumber(data.price_unit);
            const targetDiscount = toNumber(data.discount);
            const capDiscountApplied = Boolean(data.cap_discount_applied);

            if (Math.abs(toNumber(line.price_unit) - targetUnitPrice) > 1e-6) {
                line.setUnitPrice(targetUnitPrice);
                hasChanges = true;
            }
            if (Math.abs(toNumber(line.getDiscount()) - targetDiscount) > 1e-6) {
                line.setDiscount(targetDiscount);
                hasChanges = true;
            }
            if (Boolean(line.cap_discount_applied) !== capDiscountApplied) {
                line.update({ cap_discount_applied: capDiscountApplied });
                hasChanges = true;
            }
        }

        if (toNumber(order.promotional_discount_amount) !== promotionalAmount) {
            order.update({ promotional_discount_amount: promotionalAmount });
            hasChanges = true;
        }

        if (hasChanges) {
            order.triggerRecomputeAllPrices?.();
            order._markDirty?.();
        }
    },

    async _reloadBeforePaymentPage(order) {
        if (!order || typeof window === "undefined") {
            return false;
        }

        const capLines = {
            promotional_discount_amount: toNumber(order.promotional_discount_amount),
            lines: order.getOrderlines().map((line) => ({
                line_uuid: line.uuid,
                product_id: line.product_id?.id,
                price_unit: toNumber(line.price_unit),
                discount: toNumber(line.getDiscount()),
                qty: line.getQuantity(),
                cap_discount_applied: Boolean(line.cap_discount_applied),
            })),
        };

        order._markDirty?.();

        try {
            await this.data.synchronizeLocalDataInIndexedDB();
            window.sessionStorage.setItem(
                PAYMENT_RELOAD_KEY,
                JSON.stringify({
                    orderUuid: order.uuid,
                    at: Date.now(),
                    state: "reloaded",
                    capLines,
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
                capLines: payload.capLines,
            });
            return;
        }

        const capPayload = payload.capLines;
        this._reapplyCapLines(order, capPayload);
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
            console.error("[pos_discount_cap] Discount cap evaluation failed", {
                pricelistId: pricelist.id,
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

        const computation = computeCapDiscountUpdates(order, evaluations, capAmount);
        applyCapDiscountUpdates(order, computation);

        return ask(this.env.services.dialog, {
            title: _t("Discount Cap Applied"),
            body: buildCapConfirmationBody(this.env.utils, computation),
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
