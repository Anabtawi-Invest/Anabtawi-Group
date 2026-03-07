import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";

patch(ControlButtons.prototype, {
    async clickDiscount() {
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

            allowedPercents = (rows || [])
                .map((r) => Number(r.discount))
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
            if (!buffer) {
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

                if (!hasAllowed || allowedSet.some((x) => Math.abs(x - percent) < 1e-6)) {

                    const order = this.pos.getOrder();
                    const discountProductId = this.pos.config.discount_product_id?.[0];

                    if (!order) return;

                    const lines = order.getOrderlines();

                    lines.forEach((line) => {

                        const productId =
                            line.product?.id || line.product_id?.id;

                        if (!productId) return;

                        // لا يطبق الخصم على Discount Product
                        if (productId === discountProductId) return;

                        line.setDiscount(percent);
                    });
                }
            },
        });
    },
});