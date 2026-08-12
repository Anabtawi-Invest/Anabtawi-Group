/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(PosStore.prototype, {

    /**
     * Core helper: Validates if the current cashier is a manager, 
     * or prompts for a Manager Barcode / PIN.
     */
    async validateManagerAuth(actionTitle = _t("Manager Authorization Required")) {
        const cashier = this.get_cashier();
        
        // 1. If cashier is already a manager, authorize immediately
        if (cashier && (cashier.role === "manager" || cashier.is_manager)) {
            return true;
        }

        // 2. Prompt for Manager Barcode or PIN via NumberPopup
        const { confirmed, payload } = await this.popup.add(NumberPopup, {
            title: actionTitle,
            subtitle: _t("Scan Manager Barcode or Enter Manager PIN"),
            isPassword: true,
        });

        if (!confirmed || !payload) {
            return false;
        }

        const cleanInput = String(payload).trim();

        // 3. Search loaded employees for an authorized manager with matching barcode or PIN
        const managers = (this.employees || []).filter(
            (emp) => emp.role === "manager" || emp.is_manager
        );

        let authorizedManager = managers.find(
            (m) =>
                (m.barcode && String(m.barcode).trim() === cleanInput) ||
                (m.pin && (String(m.pin).trim() === cleanInput || m.pin === cleanInput))
        );

        // Fallback: If no managers filtered specifically, check all employees with manager role or matching pin
        if (!authorizedManager) {
            authorizedManager = (this.employees || []).find(
                (emp) =>
                    (emp.barcode && String(emp.barcode).trim() === cleanInput) ||
                    (emp.pin && String(emp.pin).trim() === cleanInput)
            );
            if (authorizedManager && !(authorizedManager.role === "manager" || authorizedManager.is_manager)) {
                authorizedManager = null; // Deny if employee exists but is not manager
            }
        }

        if (authorizedManager) {
            this.notification.add(
                _t("Authorized by Manager: %s", authorizedManager.name),
                3000
            );
            return true;
        } else {
            this.notification.add(
                _t("Access Denied: Invalid Manager Barcode or PIN"),
                3000
            );
            return false;
        }
    },

    /**
     * Intercept Refund Trigger
     */
    async onClickRefund() {
        if (this.config.require_manager_for_refund) {
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
        if (this.config.require_manager_for_cancel) {
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
        if (this.config.require_manager_for_discount && val !== 0 && val !== "0") {
            const ok = await this.validateManagerAuth(
                _t("Manager Barcode/PIN Required for Discount Override")
            );
            if (!ok) return;
        }
        return super.set_discount(...arguments);
    },

    async set_unit_price(val) {
        if (this.config.require_manager_for_discount) {
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
        if (this.config.require_manager_for_cash_move) {
            const ok = await this.validateManagerAuth(
                _t("Manager Barcode/PIN Required for Cash In/Out")
            );
            if (!ok) return;
        }
        return super.openCashMoveWizard(...arguments);
    }
});
