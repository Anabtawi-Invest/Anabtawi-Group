/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { ScrapPopup } from "@pos_scrap/app/screens/product_screen/scrap_popup/scrap_popup";

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
    },

    async onClickScrap() {
        const order = this.currentOrder;
        if (!order) {
            this.notification.add(_t("No active order found."), { type: "warning" });
            return;
        }

        const selectedLine = order.getSelectedOrderline?.();
        const defaultProductId = selectedLine?.product_id?.id; // keep undefined if not available (OWL props)
        const defaultQty = Number(selectedLine?.qty ?? 1) || 1;
        const defaultOrigin = order.name || order.uid || "";

        const popupProps = { defaultQty, defaultOrigin };
        if (typeof defaultProductId === "number") {
            popupProps.defaultProductId = defaultProductId;
        }

        const payload = await makeAwaitable(this.dialog, ScrapPopup, popupProps);
        if (!payload) {
            return;
        }

        try {
            const result = await this.orm.call("stock.scrap", "pos_create_scrap", [payload]);
            this.notification.add(
                _t("Scrap created: %s", result?.name || ""),
                { type: "success" }
            );
        } catch (error) {
            console.error("[POS SCRAP] Failed to create scrap:", error);
            const msg =
                error?.data?.message ||
                error?.message ||
                _t("Failed to create scrap. Please try again.");
            this.notification.add(msg, { type: "danger" });
        }
    },
});

