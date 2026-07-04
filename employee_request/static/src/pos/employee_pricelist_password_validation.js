/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { EmployeePasswordPopup } from "./employee_password_popup";

patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation() {
        const ok = await super.askBeforeValidation();
        if (ok === false) {
            return false;
        }

        const employeePricelistValue = this.pos.config.employee_pricelist_id;
        const employeePricelistId =
            employeePricelistValue?.id || employeePricelistValue || this.pos.config.raw?.employee_pricelist_id;
        if (!employeePricelistId) {
            return true;
        }

        const orderPricelistValue = this.order.pricelist_id;
        const orderPricelistId =
            orderPricelistValue?.id || orderPricelistValue || this.order.raw?.pricelist_id;
        if (!orderPricelistId || orderPricelistId !== employeePricelistId) {
            return true;
        }

        let employees = [];
        try {
            employees = await this.pos.data.call("hr.employee", "pos_employee_request_get_employees", [
                this.pos.config.id,
            ]);
        } catch (e) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: _t("Could not load employees list."),
            });
            return false;
        }

        if (!employees.length) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("No Employees"),
                body: _t("No employees are available for password verification."),
            });
            return false;
        }

        const payload = await makeAwaitable(this.pos.dialog, EmployeePasswordPopup, {
            title: _t("Employee Authorization"),
            employees,
        });

        if (!payload) {
            return false; // cancelled/closed
        }

        const { employeeId, password } = payload;
        let isValid = false;
        try {
            isValid = await this.pos.data.call("hr.employee", "pos_employee_request_check_password", [
                employeeId,
                password,
            ]);
        } catch (e) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: _t("Could not verify employee password."),
            });
            return false;
        }

        if (!isValid) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Access Denied"),
                body: _t("Employee name and password do not match."),
            });
            return false;
        }

        return true;
    },
});

