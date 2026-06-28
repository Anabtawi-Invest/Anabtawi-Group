/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

const EPSILON = 1e-6;

function toNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
}

function roundPercent(value) {
    return Math.round(toNumber(value) * 100) / 100;
}

function getLineDisplayTotal(line) {
    return Math.abs(toNumber(line.displayPrice));
}

function isOpenAmountApplicableLine(line) {
    if (!line || line.combo_parent_id) {
        return false;
    }
    if (line.isDiscountLine || line.isGlobalDiscountLine?.()) {
        return false;
    }
    if (line.isTipLine?.()) {
        return false;
    }
    return getLineDisplayTotal(line) > EPSILON;
}

function getApplicableLines(order) {
    return (order?.getOrderlines?.() || []).filter(isOpenAmountApplicableLine);
}

function snapshotLineDiscounts(lines) {
    return lines.map((line) => ({
        line,
        discount: line.getDiscount(),
    }));
}

function restoreLineDiscounts(snapshot) {
    for (const { line, discount } of snapshot) {
        line.setDiscount(discount);
    }
    const order = snapshot[0]?.line?.order_id;
    order?.triggerRecomputeAllPrices?.();
}

function getOrderDisplayTotal(order) {
    return Math.abs(toNumber(order.displayPrice));
}

/**
 * Find the total discount percentage needed on a line to reduce its display
 * total by `amountToReduce`, preserving taxes through POS price recomputation.
 */
function findDiscountForReduction(line, amountToReduce, currency) {
    const originalDiscount = line.getDiscount();
    const currentTotal = getLineDisplayTotal(line);

    if (amountToReduce >= currentTotal - EPSILON) {
        return 100;
    }

    const targetTotal = currency.round(currentTotal - amountToReduce);
    let low = originalDiscount;
    let high = 100;
    let bestDiscount = 100;

    for (let iteration = 0; iteration < 60; iteration++) {
        const mid = roundPercent((low + high) / 2);
        if (Math.abs(mid - low) < EPSILON && Math.abs(high - mid) < EPSILON) {
            break;
        }

        line.setDiscount(mid);
        line.order_id.triggerRecomputeAllPrices();
        const newTotal = getLineDisplayTotal(line);

        if (newTotal <= targetTotal + EPSILON) {
            bestDiscount = mid;
            high = mid;
        } else {
            low = mid;
        }
    }

    line.setDiscount(originalDiscount);
    line.order_id.triggerRecomputeAllPrices();
    return bestDiscount;
}

/**
 * Compute discount updates for distributing a fixed open amount across order lines.
 *
 * @returns {{ success: boolean, updates?: Array<{line: *, newDiscount: number}>, error?: string }}
 */
export function computeOpenAmountDiscountUpdates(order, enteredAmount) {
    const currency = order.currency;
    const amount = currency.round(toNumber(enteredAmount));

    if (amount <= 0) {
        return { success: false, error: _t("Amount must be greater than 0.") };
    }

    const lines = getApplicableLines(order);
    if (!lines.length) {
        return { success: false, error: _t("There are no discountable products in the order.") };
    }

    const totalAvailable = currency.round(
        lines.reduce((sum, line) => sum + getLineDisplayTotal(line), 0)
    );

    if (amount > totalAvailable + EPSILON) {
        return {
            success: false,
            error: _t(
                "The entered amount cannot be fully distributed across the order lines."
            ),
        };
    }

    let remainingAmount = amount;
    const updates = [];

    for (const line of lines) {
        if (remainingAmount <= EPSILON) {
            break;
        }

        const lineValue = getLineDisplayTotal(line);

        if (remainingAmount >= lineValue - EPSILON) {
            updates.push({ line, newDiscount: 100 });
            remainingAmount = currency.round(remainingAmount - lineValue);
            continue;
        }

        const newDiscount = findDiscountForReduction(line, remainingAmount, currency);
        updates.push({ line, newDiscount });
        remainingAmount = 0;
    }

    if (remainingAmount > EPSILON) {
        return {
            success: false,
            error: _t(
                "The entered amount cannot be fully distributed across the order lines."
            ),
        };
    }

    return { success: true, updates };
}

/**
 * Apply open amount discounts with rollback when the final total is incorrect.
 *
 * @returns {{ success: boolean, error?: string }}
 */
export function applyOpenAmountDiscount(order, enteredAmount) {
    const currency = order.currency;
    const amount = currency.round(toNumber(enteredAmount));
    const originalTotal = getOrderDisplayTotal(order);
    const expectedTotal = currency.round(originalTotal - amount);

    const lines = getApplicableLines(order);
    const snapshot = snapshotLineDiscounts(lines);

    const computation = computeOpenAmountDiscountUpdates(order, amount);
    if (!computation.success) {
        return computation;
    }

    try {
        for (const { line, newDiscount } of computation.updates) {
            line.setDiscount(newDiscount);
        }
        order.triggerRecomputeAllPrices();

        const newTotal = getOrderDisplayTotal(order);
        const delta = currency.round(newTotal - expectedTotal);
        if (!currency.isZero(delta)) {
            restoreLineDiscounts(snapshot);
            return {
                success: false,
                error: _t(
                    "The entered amount cannot be fully distributed across the order lines."
                ),
            };
        }

        order._markDirty?.();
        order.trigger?.("change", order);
        return { success: true };
    } catch {
        restoreLineDiscounts(snapshot);
        return {
            success: false,
            error: _t(
                "The entered amount cannot be fully distributed across the order lines."
            ),
        };
    }
}

export { getApplicableLines, getOrderDisplayTotal, toNumber };
