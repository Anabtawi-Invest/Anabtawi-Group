/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { CustomCakeFormPopup } from "@pos_custom_cake/app/screens/product_screen/control_buttons/cake_button/custom_cake_form_popup";
import { captureDangerNotifications } from "@pos_local_sql_backup/app/pos_store_patch";

function toNumber(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
}

function cakeFromResult(result) {
    return {
        id: result?.id || null,
        reference: result?.name || "",
        state: result?.state || "",
        partner_id: result?.partner_id || null,
        partner_name: result?.partner_name || "",
        product_name: result?.product_name || "",
        pieces: toNumber(result?.pieces),
        sugar_paste: Boolean(result?.sugar_paste),
        cake_base_cost: toNumber(result?.cake_base_cost),
        total_components_cost: toNumber(result?.total_components_cost),
        price_before_tax: toNumber(result?.price_before_tax),
        tax_amount: toNumber(result?.tax_amount),
        final_price: toNumber(result?.final_price),
        production_name: result?.production_name || "",
        date_order: result?.date_order || "",
        note: result?.note || "",
    };
}

patch(PosStore.prototype, {
    serializeOrderForLocalBackup(order) {
        const data = super.serializeOrderForLocalBackup(...arguments);
        if (order.pos_cake_order_id) {
            data.source = "cake";
            data.cake_order_id = order.pos_cake_order_id;
        }
        return data;
    },
});

patch(CustomCakeFormPopup.prototype, {
    _rememberCakeFormForBackup() {
        const size = this._getSelectedSize();
        const components = [];
        for (const category of this.categories) {
            const lineId = this.state.selectedLines[category.id];
            const line = lineId && category.lines.find((l) => l.id === lineId);
            if (line) {
                components.push({ category: category.name || "", product_name: line.product_name || "" });
            }
        }
        this.props.pos.pendingCakeFormForBackup = {
            size_name: size?.name || "",
            phone: this.state.partner?.phone || "",
            components,
            prices: { ...this.priceSummary },
        };
    },

    confirm() {
        if (this._validate()) {
            this._rememberCakeFormForBackup();
        }
        return super.confirm(...arguments);
    },

    payLater() {
        if (this._validate()) {
            this._rememberCakeFormForBackup();
        }
        return super.payLater(...arguments);
    },
});

patch(ControlButtons.prototype, {
    _recordCakeForBackup(action, result) {
        const form = this.pos.pendingCakeFormForBackup;
        this.pos.pendingCakeFormForBackup = null;
        this._cakeRecordedForBackup = true;
        this.pos.recordLocalBackupEvent(action, {
            cake: cakeFromResult(result),
            form: action === "cake_loaded" ? null : form,
            pos_order_uuid: action === "cake_pay_later" ? null : this._getCurrentOrder?.()?.uuid || null,
            raw: { result },
        });
    },

    async _runWithCakeBackup(failedAction, callback) {
        this._cakeRecordedForBackup = false;
        this._cakeBackupAction = failedAction;
        try {
            const { result, errors } = await captureDangerNotifications(this, callback);
            // A pay-later cake without manufacturing order is saved but also shows a red warning.
            if (errors.length && !this._cakeRecordedForBackup) {
                this.pos.recordLocalBackupEvent("cake_failed", {
                    failed_action: failedAction,
                    error: errors.join(" | "),
                });
            }
            return result;
        } finally {
            this._cakeBackupAction = null;
        }
    },

    async onClickCustomCake() {
        return this._runWithCakeBackup("create", () => super.onClickCustomCake(...arguments));
    },

    async onClickCakeOrders() {
        return this._runWithCakeBackup("load", () => super.onClickCakeOrders(...arguments));
    },

    async _addCakeProductToOrder({ result }) {
        const added = await super._addCakeProductToOrder(...arguments);
        if (added) {
            try {
                this._recordCakeForBackup(this._cakeBackupAction === "load" ? "cake_loaded" : "cake_created", result);
            } catch (error) {
                console.warn("[LOCAL_BACKUP] Could not record the cake order:", error);
            }
        }
        return added;
    },

    _showPayLaterReceipt(result) {
        try {
            this._recordCakeForBackup("cake_pay_later", result);
        } catch (error) {
            console.warn("[LOCAL_BACKUP] Could not record the pay-later cake order:", error);
        }
        return super._showPayLaterReceipt(...arguments);
    },
});
