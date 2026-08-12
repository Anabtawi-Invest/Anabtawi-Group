/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

/**
 * Core Helper to prompt and validate Manager Barcode or PIN
 */
async function promptAndValidateManagerAuth(posStore, actionTitle = _t("Manager Authorization Required")) {
    const dialogService = posStore?.dialog || posStore?.pos?.dialog || posStore?.env?.services?.dialog;
    if (!dialogService) {
        console.error("POS Dialog service not found");
        return true;
    }

    // NumberPopup in Odoo 19 accepts: title, subtitle, startingValue, isValid, feedback, getPayload
    const payload = await makeAwaitable(dialogService, NumberPopup, {
        title: actionTitle,
        subtitle: _t("Scan Manager Barcode or Enter Manager PIN"),
    });

    if (payload === undefined || payload === null || payload === false || payload === "") {
        return false;
    }

    const cleanInput = String(payload).trim();
    if (!cleanInput) {
        return false;
    }

    // 1. Check in-memory employees list
    let employeesList = [];
    if (posStore?.models?.["hr.employee"]) {
        employeesList = posStore.models["hr.employee"].getAll();
    } else if (posStore?.employees) {
        employeesList = posStore.employees;
    } else if (posStore?.pos?.employees) {
        employeesList = posStore.pos.employees;
    }

    let authorizedManager = employeesList.find((m) => {
        const matchBarcode = m.barcode && String(m.barcode).trim() === cleanInput;
        const matchPin = m.pin && String(m.pin).trim() === cleanInput;
        return matchBarcode || matchPin;
    });

    // 2. Fallback check via RPC if not matched in memory
    if (!authorizedManager && posStore?.data) {
        try {
            const res = await posStore.data.call("hr.employee", "search_read", [
                ['|', ['barcode', '=', cleanInput], ['pin', '=', cleanInput]],
                ['id', 'name', 'role', 'barcode', 'pin']
            ]);
            if (res && res.length > 0) {
                authorizedManager = res[0];
            }
        } catch (err) {
            console.error("RPC Manager lookup failed", err);
        }
    }

    const notif = posStore?.notification || posStore?.env?.services?.notification || posStore?.pos?.notification;

    if (authorizedManager) {
        if (notif) {
            notif.add(
                _t("Authorized by Manager: %s", authorizedManager.name || authorizedManager.display_name),
                { type: "info" }
            );
        }
        return true;
    } else {
        if (notif) {
            notif.add(
                _t("Access Denied: Invalid Manager Barcode or PIN"),
                { type: "danger" }
            );
        }
        return false;
    }
}

// ---------------------------------------------------------
// 1. PATCH POS STORE (Refunds, Cancellations, Cash Move)
// ---------------------------------------------------------
patch(PosStore.prototype, {
    async validateManagerAuth(actionTitle) {
        return promptAndValidateManagerAuth(this, actionTitle);
    },

    async onClickRefund() {
        if (this.config?.require_manager_for_refund) {
            const ok = await promptAndValidateManagerAuth(
                this,
                _t("Manager Barcode/PIN Required for Refund")
            );
            if (!ok) return;
        }
        return super.onClickRefund(...arguments);
    },

    async refundOrder(order) {
        if (this.config?.require_manager_for_refund) {
            const ok = await promptAndValidateManagerAuth(
                this,
                _t("Manager Barcode/PIN Required for Refund")
            );
            if (!ok) return;
        }
        return super.refundOrder(...arguments);
    },

    async deleteCurrentOrder() {
        if (this.config?.require_manager_for_cancel) {
            const ok = await promptAndValidateManagerAuth(
                this,
                _t("Manager Barcode/PIN Required to Cancel Order")
            );
            if (!ok) return;
        }
        return super.deleteCurrentOrder(...arguments);
    },

    async removeOrder(order) {
        if (this.config?.require_manager_for_cancel) {
            const ok = await promptAndValidateManagerAuth(
                this,
                _t("Manager Barcode/PIN Required to Cancel Order")
            );
            if (!ok) return;
        }
        return super.removeOrder(...arguments);
    },

    async openCashMoveWizard() {
        if (this.config?.require_manager_for_cash_move) {
            const ok = await promptAndValidateManagerAuth(
                this,
                _t("Manager Barcode/PIN Required for Cash In/Out")
            );
            if (!ok) return;
        }
        return super.openCashMoveWizard(...arguments);
    },

    async onClickCashMove() {
        if (this.config?.require_manager_for_cash_move) {
            const ok = await promptAndValidateManagerAuth(
                this,
                _t("Manager Barcode/PIN Required for Cash In/Out")
            );
            if (!ok) return;
        }
        if (super.onClickCashMove) {
            return super.onClickCashMove(...arguments);
        } else {
            return this.openCashMoveWizard(...arguments);
        }
    }
});

// ---------------------------------------------------------
// 2. PATCH POS ORDERLINE (Price & Discount Overrides)
// ---------------------------------------------------------
patch(PosOrderline.prototype, {
    async set_discount(val) {
        const posStore = this.models?.["pos.store"]?.get?.() || this.pos || this.env?.services?.pos_store;
        if (posStore?.config?.require_manager_for_discount && val !== 0 && val !== "0" && val !== false) {
            const ok = await promptAndValidateManagerAuth(
                posStore,
                _t("Manager Barcode/PIN Required for Discount Override")
            );
            if (!ok) return;
        }
        return super.set_discount(...arguments);
    },

    async set_unit_price(val) {
        const posStore = this.models?.["pos.store"]?.get?.() || this.pos || this.env?.services?.pos_store;
        if (posStore?.config?.require_manager_for_discount) {
            const ok = await promptAndValidateManagerAuth(
                posStore,
                _t("Manager Barcode/PIN Required for Price Override")
            );
            if (!ok) return;
        }
        return super.set_unit_price(...arguments);
    }
});

// ---------------------------------------------------------
// 3. PATCH TICKET SCREEN (Order List / Refunds / Deletions)
// ---------------------------------------------------------
try {
    patch(TicketScreen.prototype, {
        async onDoRefund() {
            if (this.pos?.config?.require_manager_for_refund) {
                const ok = await promptAndValidateManagerAuth(
                    this.pos,
                    _t("Manager Barcode/PIN Required for Refund")
                );
                if (!ok) return;
            }
            return super.onDoRefund(...arguments);
        },

        async onDeleteOrder(order) {
            if (this.pos?.config?.require_manager_for_cancel) {
                const ok = await promptAndValidateManagerAuth(
                    this.pos,
                    _t("Manager Barcode/PIN Required to Cancel Order")
                );
                if (!ok) return;
            }
            return super.onDeleteOrder(...arguments);
        }
    });
} catch (e) {
    console.warn("Could not patch TicketScreen.prototype:", e);
}
