/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PredefinedDiscountAuthPopup } from "./predefined_discount_auth_popup";
import { EmployeeDiscountAuthPopup } from "./employee_discount_auth_popup";

function getDiscountableLines(order) {
    return (order?.getOrderlines?.() || []).filter((line) =>
        typeof line.isGlobalDiscountApplicable === "function"
            ? line.isGlobalDiscountApplicable()
            : !line.isDiscountLine
    );
}

function normalizeDiscountRows(rows) {
    return (rows || []).map((row) => ({
        ...row,
        discount: Math.max(0, Math.min(100, Number(row.discount) || 0)),
    }));
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
            return false;
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
        return true;
    },

    async _ensurePartnerLoaded(partnerId) {
        let partner = this.pos.models["res.partner"].get(partnerId);
        if (partner) {
            return partner;
        }
        try {
            await this.pos.data.callRelated("res.partner", "get_new_partner", [
                this.pos.config.id,
                [["id", "=", partnerId]],
                0,
            ]);
        } catch {
            // Partner may already be partially available locally.
        }
        return this.pos.models["res.partner"].get(partnerId) || false;
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
                    ["allowed_for_employee", "=", false],
                ],
                ["id", "name", "discount", "allowed_for_employee"]
            );
            discounts = normalizeDiscountRows(rows);
        } catch {
            discounts = [];
        }

        if (discounts.length) {
            try {
                const orm = this.env.services.orm;
                const payload = await makeAwaitable(this.dialog, PredefinedDiscountAuthPopup, {
                    title: _t("Discount Authorization"),
                    discounts,
                });
                if (!payload?.discountId) {
                    return;
                }
                await orm.call(
                    "pos.predefined.discount",
                    "pos_validate_discount_authorization",
                    [payload.discountId, payload.password, false]
                );
                const selectedDiscount = discounts.find(
                    (discount) => discount.id === payload.discountId
                );
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

    async clickEmployeeDiscount() {
        const orm = this.env.services.orm;
        let discounts = [];
        let partners = [];

        try {
            const rows = await orm.searchRead(
                "pos.predefined.discount",
                [
                    ["pos_config_id", "=", this.pos.config.id],
                    ["active", "=", true],
                    ["allowed_for_employee", "=", true],
                ],
                ["id", "name", "discount", "allowed_for_employee"]
            );
            discounts = normalizeDiscountRows(rows);
        } catch {
            discounts = [];
        }

        if (!discounts.length) {
            this.env.services.notification.add(
                _t("No employee discounts are configured for this POS."),
                { type: "warning" }
            );
            return;
        }

        try {
            partners = await orm.call(
                "pos.predefined.discount",
                "pos_get_employee_partners",
                [this.pos.config.id, false, 200]
            );
        } catch {
            partners = [];
        }

        if (!partners.length) {
            this.env.services.notification.add(
                _t("No employee customers are available."),
                { type: "warning" }
            );
            return;
        }

        try {
            const payload = await makeAwaitable(this.dialog, EmployeeDiscountAuthPopup, {
                title: _t("Employee Discount"),
                discounts,
                partners,
            });
            if (!payload?.discountId || !payload?.partnerId) {
                return;
            }

            await orm.call(
                "pos.predefined.discount",
                "pos_validate_employee_discount_authorization",
                [payload.discountId, payload.partnerId, payload.password]
            );

            const selectedDiscount = discounts.find(
                (discount) => discount.id === payload.discountId
            );
            if (!selectedDiscount) {
                return;
            }

            const applied = this._applyDiscountOnAllLines(selectedDiscount.discount);
            if (!applied) {
                return;
            }

            const partner = await this._ensurePartnerLoaded(payload.partnerId);
            if (partner) {
                this.pos.setPartnerToCurrentOrder(partner);
            } else {
                this.env.services.notification.add(
                    _t("Discount applied, but the employee customer could not be loaded."),
                    { type: "warning" }
                );
            }
        } catch (error) {
            const message =
                error?.data?.message || error?.message || _t("Employee discount authorization failed.");
            this.env.services.notification.add(message, { type: "danger" });
        }
    },
});
