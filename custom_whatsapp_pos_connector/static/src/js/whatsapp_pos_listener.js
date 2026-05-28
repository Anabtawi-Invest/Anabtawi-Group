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
        this._waPollWarned = false;
        this._initWhatsappPosRealtime();
        this._logWhatsAppClientEvent("setup_initialized", {
            pos_config_id: this.config?.id || false,
        });
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
            this._logWhatsAppClientEvent("bus_notification_received", {
                count: notifications.length || 0,
            });
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
            if ((orders || []).length) {
                this._logWhatsAppClientEvent("poll_orders_received", {
                    config_id: configId,
                    count: orders.length,
                    order_ids: orders.map((o) => o.id),
                });
            }
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
            this._logWhatsAppClientEvent(
                "poll_failed",
                { message: error?.message || "unknown polling error" },
                "error"
            );
        }
    },

    _showWhatsappOrderPopup(order) {
        if (!order?.id) {
            this._logWhatsAppClientEvent("popup_skipped_invalid_order", order || {});
            return;
        }
        if (this._waShownOrderIds.has(order.id)) {
            this._logWhatsAppClientEvent("popup_skipped_duplicate", { order_id: order.id });
            return;
        }
        this._waShownOrderIds.add(order.id);
        this._logWhatsAppClientEvent("popup_opened", { order_id: order.id, name: order.name });
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
        this._logWhatsAppClientEvent("order_loaded_to_cart", {
            order_id: orderPayload.id,
            session_id: sessionId || false,
            missed_products: missedProducts,
        });

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

    async _logWhatsAppClientEvent(eventName, payload = {}, level = "info") {
        try {
            await this.env.services.orm.call("whatsapp.pos.order", "log_pos_client_event", [
                eventName,
                payload,
                level,
            ]);
        } catch (_error) {
            // Do not interrupt POS flow due to debug logging failures.
        }
    },
});
