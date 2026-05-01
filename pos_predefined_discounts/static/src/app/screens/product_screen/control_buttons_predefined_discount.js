/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PredefinedDiscountAuthPopup } from "./predefined_discount_auth_popup";

function getDiscountableLines(order) {
    return (order?.getOrderlines?.() || []).filter((line) =>
        typeof line.isGlobalDiscountApplicable === "function"
            ? line.isGlobalDiscountApplicable()
            : !line.isDiscountLine
    );
}

patch(PosStore.prototype, {
    async addLineToOrder(vals, order, opts = {}, configure = true) {
        if (order?.predefinedLineDiscountLocked && !(order.getOrderlines?.() || []).length) {
            order.predefinedLineDiscountLocked = false;
            order.predefinedLineDiscountPercent = 0;
        }
        if (order?.predefinedLineDiscountLocked && !opts.force) {
            this.dialog.add(AlertDialog, {
                title: _t("Discount Locked Order"),
                body: _t(
                    "You cannot add new lines after applying the predefined discount on all order lines. Create a new order or remove the current lines first."
                ),
            });
            return;
        }
        return await super.addLineToOrder(vals, order, opts, configure);
    },
});

patch(ControlButtons.prototype, {
    _applyDiscountOnAllLines(percent) {
        const order = this.pos.getOrder();
        const lines = getDiscountableLines(order);
        if (!order || !lines.length) {
            this.env.services.notification.add(_t("Add at least one order line first."), {
                type: "warning",
            });
            return;
        }
        for (const line of lines) {
            line.setDiscount(percent);
        }
        order.predefinedLineDiscountLocked = percent > 0;
        order.predefinedLineDiscountPercent = percent;
        this.env.services.notification.add(
            _t("Discount %s%% applied to all order lines.").replace("%s", percent),
            { type: "success" }
        );
    },

    async clickDiscount() {
        let discounts = [];
        try {
            const orm = this.env.services.orm;
            const rows = await orm.searchRead(
                "pos.predefined.discount",
                [
                    ["pos_config_id", "=", this.pos.config.id],
                    ["active", "=", true],
                ],
                ["id", "name", "discount", "is_employee_discount"]
            );
            discounts = (rows || []).map((row) => ({
                ...row,
                discount: Math.max(0, Math.min(100, Number(row.discount) || 0)),
            }));
        } catch {
            discounts = [];
        }

        if (discounts.length) {
            try {
                const orm = this.env.services.orm;
                const employees = await orm.call(
                    "hr.employee",
                    "pos_employee_request_get_employees",
                    [this.pos.config.id, false, 200]
                );
                const payload = await makeAwaitable(this.dialog, PredefinedDiscountAuthPopup, {
                    title: _t("Discount Authorization"),
                    discounts,
                    employees: employees || [],
                });
                if (!payload?.discountId) {
                    return;
                }
                await orm.call(
                    "pos.predefined.discount",
                    "pos_validate_discount_authorization",
                    [payload.discountId, payload.password, payload.employeeId || false]
                );
                const selectedDiscount = discounts.find((discount) => discount.id === payload.discountId);
                if (selectedDiscount) {
                    this._applyDiscountOnAllLines(selectedDiscount.discount);
                }
                return;
            } catch (error) {
                const message =
                    error?.data?.message || error?.message || _t("Discount authorization failed.");
                this.env.services.notification.add(message, { type: "danger" });
                return;
            }
        }

        let allowedPercents = [];
        try {
            allowedPercents = discounts
                .map((discount) => Number(discount.discount))
                .filter((x) => Number.isFinite(x))
                .map((x) => Math.max(0, Math.min(100, x)));
        } catch {
            allowedPercents = [];
        }

        const allowedSet = [...new Set(allowedPercents.map((x) => Number(x.toFixed(6))))].sort(
            (a, b) => a - b
        );
        const hasAllowed = allowedSet.length > 0;
        const isAllowed = (buffer) => {
            if (buffer === undefined || buffer === null || buffer === "") {
                return false;
            }
            const raw = this.env.utils.parseValidFloat(buffer.toString());
            if (!Number.isFinite(raw)) {
                return false;
            }
            const safe = Math.max(0, Math.min(100, raw));
            if (!hasAllowed) {
                return true;
            }
            return allowedSet.some((x) => Math.abs(x - safe) < 1e-6);
        };
        const feedback = (buffer) => {
            if (!hasAllowed) {
                return false;
            }
            if (buffer === undefined || buffer === null || buffer === "") {
                return _t("Please enter one of the predefined discounts.");
            }
            const raw = this.env.utils.parseValidFloat(buffer.toString());
            if (!Number.isFinite(raw)) {
                return _t("Please enter a valid number.");
            }
            const safe = Math.max(0, Math.min(100, raw));
            if (allowedSet.some((x) => Math.abs(x - safe) < 1e-6)) {
                return false;
            }
            return _t("Allowed discounts: %s").replace("%s", allowedSet.join(", "));
        };

        this.dialog.add(NumberPopup, {
            title: _t("Discount Percentage"),
            startingValue: this.pos.config.discount_pc,
            isValid: isAllowed,
            feedback: feedback,
            getPayload: (num) => {
                const percent = Math.max(0, Math.min(100, this.env.utils.parseValidFloat(num.toString())));
                if (!hasAllowed || allowedSet.some((x) => Math.abs(x - percent) < 1e-6)) {
                    this._applyDiscountOnAllLines(percent);
                }
            },
        });
    },
});

