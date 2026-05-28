/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { WhatsAppPosOrderPopup } from "@custom_whatsapp_pos_connector/js/whatsapp_pos_popup";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this._waShownOrderIds = new Set();
        this._waPollingInterval = null;
        this._waBusBound = false;
        this._initWhatsappPosRealtime();
    },

    _initWhatsappPosRealtime() {
        this._registerWhatsappBusChannel();
        this._startWhatsappPolling();
    },

    _registerWhatsappBusChannel() {
        if (this._waBusBound) {
            return;
        }
        const busService = this.env.services.bus_service;
        if (!busService) {
            return;
        }
        busService.addChannel("custom_whatsapp_pos_orders");
        busService.addEventListener("notification", ({ detail }) => {
            const notifications = detail || [];
            for (const item of notifications) {
                const type = item.type || item[1];
                const payload = item.payload || item[2];
                if (type === "custom_whatsapp_pos_new_order" && payload) {
                    this._showWhatsappOrderPopup(payload);
                }
            }
        });
        this._waBusBound = true;
    },

    _startWhatsappPolling() {
        if (this._waPollingInterval) {
            return;
        }
        this._fetchPendingWhatsappOrders();
        this._waPollingInterval = setInterval(() => {
            this._fetchPendingWhatsappOrders();
        }, 15000);
    },

    async _fetchPendingWhatsappOrders() {
        try {
            const configId = this.config?.id || false;
            const orders = await this.env.services.orm.call(
                "whatsapp.pos.order",
                "fetch_pending_for_pos",
                [configId, 5]
            );
            for (const order of orders || []) {
                this._showWhatsappOrderPopup(order);
            }
        } catch (error) {
            // Show one lightweight warning to help diagnose POS-side sync issues.
            if (!this._waPollWarned) {
                this._waPollWarned = true;
                this.env.services.notification.add(
                    _t("WhatsApp POS polling failed. Please refresh POS."),
                    { type: "warning" }
                );
            }
        }
    },

    _showWhatsappOrderPopup(order) {
        if (!order?.id || this._waShownOrderIds.has(order.id)) {
            return;
        }
        this._waShownOrderIds.add(order.id);
        this.env.services.dialog.add(WhatsAppPosOrderPopup, {
            order,
            onLoad: async (orderPayload) => this._loadWhatsappOrderToCart(orderPayload),
        });
    },

    async _loadWhatsappOrderToCart(orderPayload) {
        const order = this.addNewOrder();
        const partnerModel = this.models?.["res.partner"];
        const productModel = this.models?.["product.product"];

        if (orderPayload.partner_id && partnerModel && order?.set_partner) {
            const partner = partnerModel.get(orderPayload.partner_id);
            if (partner) {
                order.set_partner(partner);
            }
        }

        const missedProducts = [];
        for (const line of orderPayload.line_ids || []) {
            const product = productModel ? productModel.get(line.product_id) : null;
            if (!product) {
                missedProducts.push(line.product_name);
                continue;
            }
            if (order?.add_product) {
                order.add_product(product, {
                    quantity: Number(line.qty || 1),
                    price: Number(line.price_unit || 0),
                    merge: false,
                });
            }
        }

        const sessionId = this.pos_session?.id || false;
        await this.env.services.orm.call("whatsapp.pos.order", "mark_order_loaded", [
            orderPayload.id,
            sessionId,
        ]);

        if (missedProducts.length) {
            this.env.services.notification.add(
                _t("Loaded with missing products: %s", missedProducts.join(", ")),
                { type: "warning" }
            );
        } else {
            this.env.services.notification.add(_t("WhatsApp order loaded to POS cart."), {
                type: "success",
            });
        }
    },
});
