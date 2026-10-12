/** @odoo-module **/

import {
    localBackupCallObservers,
    serverErrorMessage,
} from "@pos_local_sql_backup/app/pos_store_patch";

const POPUP_METHODS = {
    get_delivery_amount_popup_data: "cash_delivery",
    get_closing_delivery_popup_data: "closing_delivery",
};

const PROCESS_METHODS = {
    action_process_delivery_amount: "cash_delivery",
    action_process_closing_delivery_amount: "closing_delivery",
};

// Available cash shown in the last delivery popup, per kind of delivery.
const lastPopupData = {};

function deliveryObserver({ store, model, method, args, result, error }) {
    if (model !== "pos.session") {
        return;
    }
    if (POPUP_METHODS[method]) {
        if (!error) {
            lastPopupData[POPUP_METHODS[method]] = result || {};
        }
        return;
    }
    const kind = PROCESS_METHODS[method];
    if (!kind) {
        return;
    }
    const [, amount, reason] = args;
    const popup = lastPopupData[kind] || {};
    delete lastPopupData[kind];
    const details = {
        delivery_type: kind,
        amount: Number(amount) || 0,
        reason: kind === "cash_delivery" ? reason || "" : "",
        available_cash: popup.max_amount ?? null,
        delivered_before: popup.delivered_total ?? null,
    };
    if (error || !result?.successful) {
        store.recordLocalBackupEvent("cash_delivery_failed", {
            ...details,
            error: error ? serverErrorMessage(error) : result?.message || "Refused by the server",
        });
        return;
    }
    store.recordLocalBackupEvent(kind, { ...details, receipt: result.receipt || null });
    store.syncLocalBackupCashMoves();
}

localBackupCallObservers.push(deliveryObserver);
