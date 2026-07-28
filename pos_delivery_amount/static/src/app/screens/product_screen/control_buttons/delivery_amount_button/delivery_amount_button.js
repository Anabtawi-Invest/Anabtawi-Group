/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import {
    askDeliveryAmount,
    fetchDeliveryAmountPopupData,
    processDeliveryAmount,
} from "@pos_delivery_amount/app/utils/delivery_amount_flow";

patch(ControlButtons.prototype, {
    deliveryAmountButtonClass() {
        if (this.props.showRemainingButtons) {
            return this.ui.isSmall
                ? "btn btn-warning btn-md py-2 text-start"
                : "btn btn-warning btn-lg py-5 text-start";
        }
        return "btn btn-warning btn-lg lh-lg";
    },

    get deliveryAmountButtonLabel() {
        return _t("Cash Delivery");
    },

    isDeliveryAmountEnabled() {
        const config = this.pos?.config;
        if (!config) {
            return false;
        }
        const journal = config.delivery_journal_id;
        const account = config.delivery_intermediate_account_id;
        const journalId = Array.isArray(journal) ? journal[0] : journal?.id ?? journal;
        const accountId = Array.isArray(account) ? account[0] : account?.id ?? account;
        return !!(journalId && accountId);
    },

    async onClickDeliveryAmount() {
        if (!this.isDeliveryAmountEnabled()) {
            this.notification.add(
                _t("Delivery Amount is not configured on this POS."),
                { type: "warning" }
            );
            return;
        }

        let popupData;
        try {
            popupData = await fetchDeliveryAmountPopupData(this.pos);
        } catch (error) {
            this.notification.add(
                error?.message || _t("Could not load delivery amount data."),
                { type: "danger" }
            );
            return;
        }

        if (!popupData?.configured) {
            this.notification.add(
                _t("Delivery Amount is not configured on this POS."),
                { type: "warning" }
            );
            return;
        }

        const deliveryAmount = await askDeliveryAmount(this.dialog, {
            maxAmount: popupData.max_amount,
            deliveredTotal: popupData.delivered_total,
        });
        if (deliveryAmount === undefined) {
            return;
        }

        const response = await processDeliveryAmount(this.pos, this.dialog, deliveryAmount);
        if (!response?.successful) {
            return;
        }

        this.notification.add(_t("Delivery Amount processed successfully."), { type: "success" });
    },
});
