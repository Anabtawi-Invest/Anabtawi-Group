/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
/**
 * Patch clickDiscount
 */
patch(ControlButtons.prototype, {
    async clickDiscount() {

        console.log("========== CLICK DISCOUNT BUTTON ==========");

        let allowedPercents = [];

        try {

            const orm = this.env.services.orm;

            const rows = await orm.searchRead(
                "pos.predefined.discount",
                [
                    ["pos_config_id", "=", this.pos.config.id],
                    ["active", "=", true],
                ],
                ["discount"]
            );

            console.log("ALLOWED DISCOUNTS FROM SERVER:", rows);

            allowedPercents = (rows || [])
                .map((r) => Number(r.discount))
                .filter((x) => Number.isFinite(x))
                .map((x) => Math.max(0, Math.min(100, x)));

        } catch (error) {

            console.error("ERROR FETCHING DISCOUNTS:", error);
            allowedPercents = [];
        }

        const allowedSet = [...new Set(
            allowedPercents.map((x) => Number(x.toFixed(6)))
        )].sort((a, b) => a - b);

        console.log("ALLOWED DISCOUNTS:", allowedSet);

        const hasAllowed = allowedSet.length > 0;

        const isAllowed = (buffer) => {

            const raw = this.env.utils.parseValidFloat(buffer?.toString());
            const safe = Math.max(0, Math.min(100, raw));

            return !hasAllowed || allowedSet.some((x) => Math.abs(x - safe) < 1e-6);
        };

        const feedback = (buffer) => {

            const raw = this.env.utils.parseValidFloat(buffer?.toString());

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

                const percent = Math.max(
                    0,
                    Math.min(100, this.env.utils.parseValidFloat(num.toString()))
                );

                console.log("DISCOUNT ENTERED:", percent);

                if (!hasAllowed || allowedSet.some((x) => Math.abs(x - percent) < 1e-6)) {

                    console.log("CALLING applyDiscount()");
                    this.applyDiscount(percent);

                } else {

                    console.log("DISCOUNT NOT ALLOWED");

                }
            },
        });
    },
});


/**
 * Patch applyDiscount
 */
patch(ControlButtons.prototype, {

    applyDiscount(percent) {

        console.log("========== APPLY DISCOUNT START ==========");

        const order = this.pos.getOrder();

        if (!order) {
            console.log("NO ORDER FOUND");
            return;
        }

        const lines = order.getOrderlines();

        console.log("TOTAL ORDER LINES:", lines.length);

        // تحقق إذا كان يوجد rounding product
        const hasRoundingProduct = lines.some((line) => {
            const productId = line.product?.id || line.product_id?.id;
            return productId === 30;
        });

       if (hasRoundingProduct) {

    console.log("ROUNDING PRODUCT FOUND → DISCOUNT BLOCKED");

    this.dialog.add(AlertDialog, {
        title: _t("Discount Not Allowed"),
        body: _t("Cannot apply discount when rounding product exists."),
    });

    return;
}

        // تطبيق الخصم
        lines.forEach((line) => {

            const productId = line.product?.id || line.product_id?.id;

            console.log("APPLYING DISCOUNT TO:", productId);

            line.setDiscount(percent);
        });

        console.log("========== APPLY DISCOUNT FINISHED ==========");
    },
});