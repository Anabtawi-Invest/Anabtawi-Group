/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(PosStore.prototype, {

    /**
     * Core helper: Validates if the current cashier is a manager, 
     * or prompts for a Manager Barcode / PIN via NumberPopup.
     */
    async validateManagerAuth(actionTitle = _t("Manager Authorization Required")) {
        const cashier = this.get_cashier?.() || this.cashier;
        
        // 1. If cashier is already a manager, authorize immediately
        if (cashier && (cashier.role === "manager" || cashier.is_manager)) {
            return true;
        }

        // 2. Prompt for Manager Barcode or PIN via NumberPopup using makeAwaitable
        const dialogService = this.dialog || this.pos?.dialog;
        if (!dialogService) {
            console.error("POS Dialog service not found");
            return true;
        }

        const payload = await makeAwaitable(dialogService, NumberPopup, {
            title: actionTitle,
            subtitle: _t("Scan Manager Barcode or Enter Manager PIN"),
            isPassword: true,
        });

        if (payload === undefined || payload === null || payload === false) {
            return false;
        }

        const cleanInput = String(payload).trim();
        if (!cleanInput) {
            return false;
        }

        // 3. Search loaded employees for an authorized manager with matching barcode or PIN
        const employeesList = this.models?.["hr.employee"]?.getAll() || this.employees || [];
        
        const managers = employeesList.filter(
            (emp) => emp.role === "manager" || emp.is_manager
        );

        let authorizedManager = managers.find(
            (m) =>
                (m.barcode && String(m.barcode).trim() === cleanInput) ||
                (m.pin && String(m.pin).trim() === cleanInput)
        );

        // Fallback: Check all employees if manager role flag was not loaded
        if (!authorizedManager) {
            const foundEmp = employeesList.find(
                (emp) =>
                    (emp.barcode && String(emp.barcode).trim() === cleanInput) ||
                    (emp.pin && String(emp.pin).trim() === cleanInput)
            );
            if (foundEmp && (foundEmp.role === "manager" || foundEmp.is_manager)) {
                authorizedManager = foundEmp;
            }
        }

        if (authorizedManager) {
            if (this.notification) {
                this.notification.add(
                    _t("Authorized by Manager: %s", authorizedManager.name),
                    { type: "info" }
                );
            }
            return true;
        } else {
            if (this.notification) {
                this.notification.add(
                    _t("Access Denied: Invalid Manager Barcode or PIN"),
                    { type: "danger" }
                );
            }
            return false;
        }
    },

    /**
     * Intercept Refund Trigger
     */
    async onClickRefund() {
        if (this.config?.require_manager_for_refund) {
            const ok = await this.validateManagerAuth(
                _t("Manager Barcode/PIN Required for Refund")
            );
            if (!ok) return;
        }
        return super.onClickRefund(...arguments);
    },

    /**
     * Intercept Order Cancellation / Deletion
     */
    async deleteCurrentOrder() {
        if (this.config?.require_manager_for_cancel) {
            const ok = await this.validateManagerAuth(
                _t("Manager Barcode/PIN Required to Cancel Order")
            );
            if (!ok) return;
        }
        return super.deleteCurrentOrder(...arguments);
    },

    /**
     * Intercept Manual Price & Discount Overrides on Order Line
     */
    async set_discount(val) {
        if (this.config?.require_manager_for_discount && val !== 0 && val !== "0") {
            const ok = await this.validateManagerAuth(
                _t("Manager Barcode/PIN Required for Discount Override")
            );
            if (!ok) return;
        }
        return super.set_discount(...arguments);
    },

    async set_unit_price(val) {
        if (this.config?.require_manager_for_discount) {
            const ok = await this.validateManagerAuth(
                _t("Manager Barcode/PIN Required for Price Override")
            );
            if (!ok) return;
        }
        return super.set_unit_price(...arguments);
    },

    /**
     * Intercept Cash In / Cash Out
     */
    async openCashMoveWizard() {
        if (this.config?.require_manager_for_cash_move) {
            const ok = await this.validateManagerAuth(
                _t("Manager Barcode/PIN Required for Cash In/Out")
            );
            if (!ok) return;
        }
        return super.openCashMoveWizard(...arguments);
    }
});
