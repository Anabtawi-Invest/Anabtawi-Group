/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { rpc } from "@web/core/network/rpc";
import { CustomCakeFormPopup } from "./custom_cake_form_popup";
import { CakeOrdersListPopup } from "./cake_orders_list_popup";
import { CakePayLaterReceipt } from "./cake_pay_later_receipt";

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");
        this.printer = useService("printer");
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
        return {
            companyName: this.pos.company?.name || "",
            posName: this.pos.config?.name || "",
            reference: result?.name || "",
            date: new Date().toLocaleString(),
            customerName: partner?.name || result?.partner_name || "",
            productName: result?.product_name || "",
            pieces: result?.pieces || 0,
            finalPrice: result?.final_price || 0,
            currencyId: this.pos.currency?.id,
        };
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
                this.notification.add(
                    _t("Cake order saved: %s", result?.name || ""),
                    { type: "success" }
                );
                try {
                    await this.printer.print(
                        CakePayLaterReceipt,
                        {
                            receipt: this._buildPayLaterReceiptData(result, popupResult.partner),
                        },
                        this.pos.printOptions
                    );
                } catch (printError) {
                    const printMessage =
                        printError?.body ||
                        printError?.message ||
                        _t("Order saved but receipt printing failed.");
                    this.notification.add(printMessage, { type: "warning" });
                }
                return;
            }

            const added = await this._addCakeProductToOrder({
                result,
                partnerId: popupResult.partner?.id,
            });
            if (added) {
                this.notification.add(
                    _t("Custom cake added: %s", result?.name || ""),
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
