/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

export function parsePaymentAmount(value) {
    const normalized = String(value ?? "")
        .trim()
        .replace(",", ".");
    if (!normalized) {
        return 0;
    }
    const parsed = parseFloat(normalized);
    return Number.isFinite(parsed) ? parsed : 0;
}

export function initPaymentAmounts(paymentMethods, totalAmount) {
    const amounts = {};
    for (const pm of paymentMethods || []) {
        amounts[pm.id] = "0";
    }
    if (paymentMethods?.length && totalAmount > 0) {
        amounts[paymentMethods[0].id] = String(totalAmount);
    }
    return amounts;
}

export function buildPaymentLines(paymentMethods, paymentAmounts) {
    const lines = [];
    for (const pm of paymentMethods || []) {
        const amount = parsePaymentAmount(paymentAmounts[pm.id]);
        if (amount > 0) {
            lines.push({
                payment_method_id: pm.id,
                payment_method_name: pm.name,
                amount,
            });
        }
    }
    return lines;
}

export function paymentLinesTotal(paymentLines) {
    return (paymentLines || []).reduce((sum, line) => sum + (line.amount || 0), 0);
}

export function validatePaymentLinesTotal(paymentLines, requiredTotal, currency, tolerance = 0.01) {
    const total = paymentLinesTotal(paymentLines);
    if (!paymentLines?.length) {
        return _t("Please allocate at least one payment method.");
    }
    if (Math.abs(total - requiredTotal) > tolerance) {
        return _t(
            "Payment methods must total %(required)s (currently %(current)s).",
            { required: requiredTotal, current: total }
        );
    }
    return null;
}

export function allocatedTotalFmt(paymentMethods, paymentAmounts, currencyId, formatCurrency) {
    const lines = buildPaymentLines(paymentMethods, paymentAmounts);
    return formatCurrency(paymentLinesTotal(lines), currencyId);
}
