/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ConnectionLostError, RPCError } from "@web/core/network/rpc";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { DeliveryAmountPopup } from "@pos_delivery_amount/app/components/delivery_amount_popup/delivery_amount_popup";
import { DeliveryAmountReceipt } from "@pos_delivery_amount/app/components/delivery_amount_receipt/delivery_amount_receipt";

export function extractDeliveryAmountErrorMessage(error) {
    if (error instanceof RPCError) {
        return (
            error?.data?.arguments?.[0] ||
            error?.data?.message ||
            error?.message ||
            _t("An error occurred while processing Delivery Amount.")
        );
    }
    return error?.message || _t("An error occurred while processing Delivery Amount.");
}

export async function fetchDeliveryAmountPopupData(pos) {
    return pos.data.call("pos.session", "get_delivery_amount_popup_data", [pos.session.id]);
}

export async function fetchClosingDeliveryPopupData(pos) {
    return pos.data.call("pos.session", "get_closing_delivery_popup_data", [pos.session.id]);
}

/**
 * @returns {Promise<{amount: number, reason: string}|undefined>}
 */
export async function askDeliveryAmount(
    dialog,
    {
        maxAmount,
        deliveredTotal = 0,
        title = _t("Cash Delivery"),
        fieldLabel = _t("Amount to be out"),
        requireReason = false,
    }
) {
    const deliveredLabel = deliveredTotal
        ? _t("Available Cash (already delivered: %s)", deliveredTotal)
        : _t("Available Cash");

    while (true) {
        const result = await makeAwaitable(dialog, DeliveryAmountPopup, {
            defaultAmount: 0,
            maxAmount,
            title,
            fieldLabel,
            maxLabel: deliveredLabel,
            requireReason,
        });

        if (result === undefined) {
            return undefined;
        }

        const amount = result?.amount;
        const reason = (result?.reason || "").trim();

        if (amount < 0) {
            await makeAwaitable(dialog, AlertDialog, {
                title: _t("Cash Delivery"),
                body: _t("Delivery Amount must be positive or zero."),
            });
            continue;
        }

        if (amount > maxAmount) {
            await makeAwaitable(dialog, AlertDialog, {
                title: _t("Cash Delivery"),
                body: _t("Delivery Amount cannot exceed available cash balance."),
            });
            continue;
        }

        if (requireReason && !reason) {
            await makeAwaitable(dialog, AlertDialog, {
                title: _t("Cash Delivery"),
                body: _t("A reason is required for cash delivery."),
            });
            continue;
        }

        if (dialog.env?.utils?.isZero?.(amount)) {
            const proceed = await ask(dialog, {
                title: _t("Cash Delivery"),
                body: _t("Are you sure the Delivery Amount is zero?"),
                confirmLabel: _t("Yes"),
                cancelLabel: _t("No"),
            });
            if (!proceed) {
                continue;
            }
        }

        return { amount, reason };
    }
}

export async function processDeliveryAmount(pos, dialog, amount, reason) {
    try {
        return await pos.data.call(
            "pos.session",
            "action_process_delivery_amount",
            [pos.session.id, amount, reason]
        );
    } catch (error) {
        if (error instanceof ConnectionLostError) {
            throw error;
        }
        await makeAwaitable(dialog, AlertDialog, {
            title: _t("Cash Delivery"),
            body: extractDeliveryAmountErrorMessage(error),
        });
        return null;
    }
}

export async function processClosingDeliveryAmount(pos, dialog, amount) {
    try {
        return await pos.data.call(
            "pos.session",
            "action_process_closing_delivery_amount",
            [pos.session.id, amount]
        );
    } catch (error) {
        if (error instanceof ConnectionLostError) {
            throw error;
        }
        await makeAwaitable(dialog, AlertDialog, {
            title: _t("Closing Delivery Amount"),
            body: extractDeliveryAmountErrorMessage(error),
        });
        return null;
    }
}

/**
 * Print a cash delivery receipt via the POS printer (browser fallback).
 * Does not include session name or reason. Failures do not block the flow.
 */
export async function printDeliveryAmountReceipt(pos, receipt, { isClosing = false } = {}) {
    if (!receipt || !pos?.printer) {
        return false;
    }
    if (pos.currency?.isZero?.(receipt.amount ?? 0)) {
        return false;
    }
    try {
        const result = await pos.printer.print(
            DeliveryAmountReceipt,
            {
                title: isClosing ? _t("Closing Delivery Amount") : _t("Cash Delivery"),
                companyName: receipt.company_name || "",
                posName: receipt.pos_name || "",
                cashier: receipt.cashier || "",
                formattedAmount: receipt.formatted_amount || "",
                date: receipt.date || "",
                moveName: receipt.move_name || "",
            },
            pos.printOptions || { webPrintFallback: true }
        );
        return Boolean(result);
    } catch (error) {
        console.warn("[pos_delivery_amount] Could not print delivery receipt.", error);
        return false;
    }
}
