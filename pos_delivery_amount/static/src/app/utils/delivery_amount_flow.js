/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ConnectionLostError, RPCError } from "@web/core/network/rpc";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { DeliveryAmountPopup } from "@pos_delivery_amount/app/components/delivery_amount_popup/delivery_amount_popup";

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

export async function askDeliveryAmount(
    dialog,
    { maxAmount, deliveredTotal = 0, title = _t("Cash Delivery"), fieldLabel = _t("Delivery Amount") }
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
        });

        if (result === undefined) {
            return undefined;
        }

        if (result < 0) {
            await makeAwaitable(dialog, AlertDialog, {
                title: _t("Cash Delivery"),
                body: _t("Delivery Amount must be positive or zero."),
            });
            continue;
        }

        if (result > maxAmount) {
            await makeAwaitable(dialog, AlertDialog, {
                title: _t("Cash Delivery"),
                body: _t("Delivery Amount cannot exceed available cash balance."),
            });
            continue;
        }

        if (dialog.env?.utils?.isZero?.(result)) {
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

        return result;
    }
}

export async function processDeliveryAmount(pos, dialog, amount) {
    try {
        return await pos.data.call(
            "pos.session",
            "action_process_delivery_amount",
            [pos.session.id, amount]
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
