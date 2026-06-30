/** @odoo-module **/

export function toNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
}

export function toPercentFromPrices(basePrice, discountedPrice) {
    const base = toNumber(basePrice);
    const discounted = toNumber(discountedPrice);
    if (base <= 0) {
        return 0;
    }
    const percent = ((base - discounted) / base) * 100;
    return Math.max(0, Math.min(100, percent));
}

export function roundPercent(value) {
    return Math.round(toNumber(value) * 100) / 100;
}

/**
 * Apply pricelist discount sequentially until the monetary cap is reached.
 * Only the last affected line may receive a reduced percentage.
 */
export function computeSequentialCapDiscounts({ order, evaluations, capAmount }) {
    const byLineUuid = new Map((evaluations || []).map((item) => [item.line_uuid, item]));
    const lineUpdates = new Map();
    let accumulatedDiscount = 0;
    let capReached = false;
    let consumedAmount = 0;
    let eligibleLines = 0;
    let adjustedLines = 0;
    let excludedAfterCapLines = 0;

    for (const line of order.getOrderlines()) {
        const data = byLineUuid.get(line.uuid);
        if (!data?.cap_eligible || !data.can_apply_cap) {
            continue;
        }

        eligibleLines += 1;
        const qty = Math.abs(line.getQuantity());
        const baseUnitPrice = toNumber(data.base_unit_price) || toNumber(line.price_unit);
        const lineAmount = order.currency.round(qty * baseUnitPrice);
        const fullDiscountPercent = roundPercent(
            toNumber(data.pricelist_discount_percent) ||
                toPercentFromPrices(baseUnitPrice, data.discounted_unit_price)
        );
        const fullDiscountAmount = order.currency.round(
            toNumber(data.line_full_discount_amount) ||
                lineAmount * (fullDiscountPercent / 100)
        );

        let targetDiscountPercent = 0;

        if (capReached) {
            excludedAfterCapLines += 1;
        } else if (fullDiscountPercent <= 0 || lineAmount <= 0) {
            targetDiscountPercent = 0;
        } else if (accumulatedDiscount + fullDiscountAmount <= capAmount + 1e-9) {
            targetDiscountPercent = fullDiscountPercent;
            accumulatedDiscount = order.currency.round(accumulatedDiscount + fullDiscountAmount);
            consumedAmount = accumulatedDiscount;
        } else {
            const remainingDiscount = order.currency.round(capAmount - accumulatedDiscount);
            targetDiscountPercent = roundPercent(
                Math.min(fullDiscountPercent, (remainingDiscount / lineAmount) * 100)
            );
            adjustedLines += 1;
            capReached = true;
            consumedAmount = capAmount;
            accumulatedDiscount = capAmount;
        }

        lineUpdates.set(line.uuid, {
            targetBaseUnitPrice: baseUnitPrice,
            targetDiscountPercent: roundPercent(targetDiscountPercent),
        });
    }

    return {
        lineUpdates,
        consumedAmount,
        remainingCap: Math.max(0, order.currency.round(capAmount - consumedAmount)),
        eligibleLines,
        adjustedLines,
        excludedAfterCapLines,
    };
}

export function applyCapLineUpdates(order, lineUpdates) {
    let hasChanges = false;

    for (const line of order.getOrderlines()) {
        const update = lineUpdates.get(line.uuid);
        if (!update) {
            continue;
        }
        const targetUnitPrice = toNumber(update.targetBaseUnitPrice);
        const targetDiscount = toNumber(update.targetDiscountPercent);

        if (Math.abs(toNumber(line.price_unit) - targetUnitPrice) > 1e-6) {
            line.setUnitPrice(targetUnitPrice);
            hasChanges = true;
        }
        if (Math.abs(toNumber(line.getDiscount()) - targetDiscount) > 1e-6) {
            line.setDiscount(targetDiscount);
            hasChanges = true;
        }
    }

    if (hasChanges) {
        order.triggerRecomputeAllPrices?.();
        order._markDirty?.();
    }

    return hasChanges;
}
