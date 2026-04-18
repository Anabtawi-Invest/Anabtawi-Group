/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { _t } from "@web/core/l10n/translation";

patch(ControlButtons.prototype, {
    async applyRounding() {
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

        const amountWithTax = this.env.utils.parseValidFloat(payload?.toString() || "");

if (isNaN(amountWithTax) || amountWithTax <= 0) {
    this.notification.add(_t("Please enter a valid amount."), { type: "warning" });
    return;
}

// 🔒 Restrict to maximum 0.09
if (amountWithTax > 0.099) {
    this.notification.add(
        _t("Maximum allowed rounding amount is 0.099."),
        { type: "warning" }
    );
    return;
}


        const adjustmentId = extractId(adjustmentProduct);
        if (!adjustmentId) {
            this.notification.add(_t("Adjustment product not loaded in POS."), { type: "danger" });
            return;
        }

        order
            .getOrderlines()
            .filter((line) => extractId(line?.product_id) === adjustmentId)
            .forEach((line) => order.removeOrderline(line));

        const totalBefore = order.priceIncl;
        const targetDecrease = Math.abs(amountWithTax);
        const taxRate = (adjustmentProduct.taxes_id?.[0]?.amount || 0) / 100;
        const initialBaseAmount = targetDecrease / (1 + taxRate);

        const adjustmentLine = await this.pos.addLineToCurrentOrder(
            {
                product_tmpl_id: adjustmentProduct.product_tmpl_id,
                product_id: adjustmentProduct,
                price_unit: -initialBaseAmount,
                qty: 1,
            },
            {},
            false
        );

        if (!adjustmentLine) {
            this.notification.add(_t("Could not create adjustment line."), { type: "danger" });
            return;
        }

        const setPreciseUnitPrice = (line, value) => {
            // Avoid setUnitPrice() here because it rounds to Product Price precision.
            // We need higher precision to hit tax-included target deltas exactly.
            line.update({ price_unit: Number(value) || 0 });
        };

        const currencyRounding = this.pos.currency?.rounding || 0.01;
        const tolerance = Math.max(currencyRounding / 2, 0.000001);
        const getDecrease = () => totalBefore - order.priceIncl;
        const getResidual = () => targetDecrease - getDecrease();

        // Adjust the line price so the order total decreases by the exact entered tax-included amount.
        let residual = getResidual();
        const probeStep = Math.max(currencyRounding, 0.01);
        for (let i = 0; i < 12 && Math.abs(residual) > tolerance; i++) {
            const base = adjustmentLine.price_unit;
            setPreciseUnitPrice(adjustmentLine, base + probeStep);
            const decreasePlus = getDecrease();
            setPreciseUnitPrice(adjustmentLine, base);
            const decreaseBase = getDecrease();
            const slope = (decreasePlus - decreaseBase) / probeStep;

            if (!Number.isFinite(slope) || Math.abs(slope) < 1e-9) {
                break;
            }

            setPreciseUnitPrice(adjustmentLine, base + residual / slope);
            residual = getResidual();
        }

        // Fallback discrete search around the computed unit price to absorb line-level tax rounding.
        if (Math.abs(residual) > tolerance) {
            const center = adjustmentLine.price_unit;
            const searchStep = Math.max(currencyRounding / 10, 0.0001);
            let bestUnitPrice = center;
            let bestError = Math.abs(residual);
            for (let n = -400; n <= 400; n++) {
                const candidate = center + n * searchStep;
                setPreciseUnitPrice(adjustmentLine, candidate);
                const error = Math.abs(getResidual());
                if (error < bestError) {
                    bestError = error;
                    bestUnitPrice = candidate;
                    if (bestError <= tolerance) {
                        break;
                    }
                }
            }
            setPreciseUnitPrice(adjustmentLine, bestUnitPrice);
            residual = getResidual();
        }

        if (Math.abs(residual) > tolerance) {
            this.notification.add(
                _t("Applied amount is very close but not exact due to tax rounding."),
                { type: "warning" }
            );
        }
    },
});
