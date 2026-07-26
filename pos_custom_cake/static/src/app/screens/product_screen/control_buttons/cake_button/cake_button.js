/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { rpc } from "@web/core/network/rpc";
import { formatCurrency } from "@web/core/currency";
import { CustomCakeFormPopup } from "./custom_cake_form_popup";
import { CakeOrdersListPopup } from "./cake_orders_list_popup";
import { CakePayLaterReceiptPopup } from "./cake_pay_later_receipt_popup";

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");
    },

    customCakeButtonClass() {
        return this.ui.isSmall
            ? "btn btn-md py-3 text-start w-100"
            : "btn btn-lg py-5 text-start w-100";
    },

    customCakeButtonStyle() {
        return "background: linear-gradient(135deg, #ff9ed2 0%, #ff69b4 45%, #e91e8c 100%); color: #fff; border: none;";
    },

    customCakeIconStyle() {
        return "font-size: 2.75rem; line-height: 1; filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));";
    },

    cakeOrdersButtonClass() {
        if (this.props.showRemainingButtons) {
            return this.ui.isSmall
                ? "btn btn-secondary btn-md py-2 text-start"
                : "btn btn-secondary btn-lg py-5 text-start";
        }
        return "btn btn-secondary btn-lg lh-lg";
    },

    get customCakeButtonLabel() {
        return _t("Custom Cake");
    },

    get cakeOrdersButtonLabel() {
        return _t("Cake Orders");
    },

    isCustomCakeEnabled() {
        const cfg = this.pos?.config;
        if (!cfg) {
            return false;
        }
        // Default to enabled when field is missing from POS data (undefined).
        return cfg.enable_custom_cake !== false;
    },

    _getCurrentOrder() {
        return this.currentOrder || this.pos.getOrder?.();
    },

    async _ensurePartner(partnerId) {
        let partner = this.pos.models["res.partner"].get(partnerId);
        if (partner) {
            return partner;
        }
        const records = await this.orm.read("res.partner", [partnerId], ["name", "phone", "mobile"]);
        if (records?.length) {
            partner = this.pos.models["res.partner"].create(records[0]);
        }
        return partner;
    },

    async _addCakeProductToOrder({ result, partnerId }) {
        const order = this._getCurrentOrder();
        if (!order) {
            this.notification.add(_t("No active order found."), { type: "warning" });
            return false;
        }

        const partner = partnerId ? await this._ensurePartner(partnerId) : null;
        if (partner) {
            order.setPartner(partner);
        }

        const product = this.pos.models["product.product"].get(result.product_id);
        if (!product) {
            this.notification.add(_t("Cake product not found in POS."), { type: "danger" });
            return false;
        }

        await this.pos.addLineToCurrentOrder(
            {
                product_tmpl_id: product.product_tmpl_id,
                qty: 1,
                price_unit: result.price_before_tax,
            },
            {},
            false
        );

        order.setPosCakeOrderId(result.id);
        return true;
    },

    _buildPayLaterReceiptData(result, partner) {
        const finalPrice = result?.final_price || 0;
        return {
            companyName: this.pos.company?.name || "",
            posName: this.pos.config?.name || "",
            reference: result?.name || "",
            date: new Date().toLocaleString(),
            customerName: partner?.name || result?.partner_name || "",
            productName: result?.product_name || "",
            pieces: result?.pieces || 0,
            finalPrice,
            currencyId: this.pos.currency?.id,
            title: _t("Custom Cake Order"),
            orderNumberLabel: _t("Order Number"),
            dateLabel: _t("Date"),
            customerLabel: _t("Customer"),
            statusLabel: _t("Status"),
            statusText: _t("Waiting for Payment"),
            piecesLabel: _t("Pieces"),
            totalLabel: _t("Total"),
            finalPriceFormatted: formatCurrency(finalPrice, this.pos.currency?.id),
            footerText: _t("Please pay at the counter when ready."),
        };
    },

    _showPayLaterReceipt(result, partner) {
        const receipt = this._buildPayLaterReceiptData(result, partner);
        this.dialog.add(CakePayLaterReceiptPopup, {
            receipt,
        });
    },

    async onClickCustomCake() {
        if (!this.isCustomCakeEnabled()) {
            this.notification.add(_t("Custom Cake is not enabled on this POS."), { type: "warning" });
            return;
        }

        const popupResult = await makeAwaitable(this.dialog, CustomCakeFormPopup, {
            pos: this.pos,
        });
        if (!popupResult) {
            return;
        }

        try {
            const result = await rpc("/pos/custom_cake/create_order", popupResult.payload);

            if (popupResult.action === "pay_later") {
                const moLabel = result?.production_name
                    ? _t("MO: %s", result.production_name)
                    : "";
                this.notification.add(
                    _t("Cake order saved: %s %s", result?.name || "", moLabel).trim(),
                    { type: "success" }
                );
                if (!result?.production_id) {
                    this.notification.add(
                        _t(
                            "No manufacturing order was linked. Upgrade the module and use Create Manufacturing Order on the cake order form."
                        ),
                        { type: "danger" }
                    );
                }
                this._showPayLaterReceipt(result, popupResult.partner);
                return;
            }

            const added = await this._addCakeProductToOrder({
                result,
                partnerId: popupResult.partner?.id,
            });
            if (added) {
                const moLabel = result?.production_name
                    ? _t("MO: %s", result.production_name)
                    : "";
                this.notification.add(
                    _t("Custom cake added: %s %s", result?.name || "", moLabel).trim(),
                    { type: "success" }
                );
            }
        } catch (error) {
            const msg =
                error?.data?.message || error?.message || _t("Failed to create custom cake order.");
            this.notification.add(msg, { type: "danger" });
        }
    },

    async onClickCakeOrders() {
        if (!this.isCustomCakeEnabled()) {
            this.notification.add(_t("Custom Cake is not enabled on this POS."), { type: "warning" });
            return;
        }

        const popupResult = await makeAwaitable(this.dialog, CakeOrdersListPopup, {
            pos: this.pos,
        });
        if (!popupResult?.order) {
            return;
        }

        try {
            const result = await rpc("/pos/custom_cake/get_order", {
                order_id: popupResult.order.id,
            });

            const added = await this._addCakeProductToOrder({
                result,
                partnerId: result.partner_id,
            });
            if (added) {
                this.notification.add(
                    _t("Cake order loaded: %s", result?.name || ""),
                    { type: "success" }
                );
            }
        } catch (error) {
            const msg =
                error?.data?.message || error?.message || _t("Failed to load cake order.");
            this.notification.add(msg, { type: "danger" });
        }
    },
});
