/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { _t } from "@web/core/l10n/translation";

patch(ControlButtons.prototype, {
    async applyDiscount() {
        const order = this.currentOrder;
        if (!order) {
            return;
        }

        if (!order.getOrderlines().length) {
            this.notification.add(_t("There are no products in the order."), { type: "warning" });
            return;
        }

        const extractId = (value) => {
            if (Array.isArray(value)) {
                return value[0] ?? null;
            }
            if (typeof value === "number") {
                return value;
            }
            if (value && typeof value === "object") {
                return value.id ?? null;
            }
            return null;
        };

        let adjustmentProductId = extractId(this.pos.config?.discount_adjustment_product_id);

        // Fallback for stale frontend cache: fetch config value directly from backend.
        if (!adjustmentProductId && this.pos.config?.id) {
            try {
                const configData = await this.pos.data.call("pos.config", "read", [
                    [this.pos.config.id],
                    ["discount_adjustment_product_id"],
                ]);
                adjustmentProductId = extractId(configData?.[0]?.discount_adjustment_product_id);
            } catch {
                // Keep silent; user-facing message below is enough.
            }
        }

        if (!adjustmentProductId) {
            this.notification.add(_t("Please configure Discount Adjustment Product in POS settings."), {
                type: "danger",
            });
            return;
        }

        const productModel = this.pos.models["product.product"];
        let adjustmentProduct = productModel?.get(adjustmentProductId);

        if (!adjustmentProduct) {
            try {
                const records = await this.pos.loadNewProducts([
                    ["product_variant_ids", "in", [adjustmentProductId]],
                    ["available_in_pos", "=", true],
                    ["sale_ok", "=", true],
                ]);
                const products = records?.["product.product"] || [];
                adjustmentProduct = products.find((product) => extractId(product) === adjustmentProductId);
            } catch {
                // Keep silent; user-facing message below is enough.
            }
        }

        if (!adjustmentProduct) {
            this.notification.add(_t("Adjustment product not loaded in POS."), { type: "danger" });
            return;
        }

        const payload = await makeAwaitable(this.dialog, NumberPopup, {
            title: _t("Enter Rounding Amount"),
            startingValue: 0,
        });

        if (payload === undefined) {
            return;
        }

        const amountWithTax = parseFloat(payload);
        if (isNaN(amountWithTax) || amountWithTax <= 0) {
            this.notification.add(_t("Please enter a valid amount."), { type: "warning" });
            return;
        }

        const adjustmentId = extractId(adjustmentProduct);
        if (!adjustmentId) {
            this.notification.add(_t("Adjustment product not loaded in POS."), { type: "danger" });
            return;
        }

        const taxRate = (adjustmentProduct.taxes_id?.[0]?.amount || 0) / 100;
        const baseAmount = amountWithTax / (1 + taxRate);

        order
            .getOrderlines()
            .filter((line) => extractId(line?.product_id) === adjustmentId)
            .forEach((line) => order.removeOrderline(line));

        await this.pos.addLineToCurrentOrder(
            {
                product_tmpl_id: adjustmentProduct.product_tmpl_id,
                product_id: adjustmentProduct,
                price_unit: -baseAmount,
                qty: 1,
            },
            {},
            false
        );
    },
});
