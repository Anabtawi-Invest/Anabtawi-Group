/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { rpc, RPCError } from "@web/core/network/rpc";
import { serializeDateTime } from "@web/core/l10n/dates";
import { SelfOrder } from "@pos_self_order/app/services/self_order_service";
import { _t } from "@web/core/l10n/translation";

const TRACKED_REQUEST_STATES = new Set(["new", "accepted", "done", "cancelled"]);
const TRACKED_ORDERS_STORAGE_KEY = "pos_self_order_location.tracked_orders";
const CUSTOMER_SESSION_STORAGE_KEY = "pos_self_order_location.customer_session";
const REQUEST_STATUS_POLL_MS = 5000;

patch(SelfOrder.prototype, {
    async setup(...args) {
        this._requestStateListeners = new Set();
        this._trackedOrderAccessTokens = new Set();
        this.orderRequestStatuses = {};
        this.customerSession = null;
        this._restoreTrackedOrders();
        this._restoreCustomerSession();

        await super.setup(...args);

        if (this.requiresCustomerPhone()) {
            await this.validateCustomerSession();
        }

        this.data.connectWebSocket("SELF_ORDER_REQUEST_UPDATED", (payload) => {
            if (!payload?.order_access_token) {
                return;
            }
            this._applyOrderRequestStatus(payload.order_access_token, {
                state: payload.state,
                name: payload.name,
            });
        });

        if (this.usesPaymentChoice()) {
            this._startGlobalRequestStatusPolling();
            this._syncTrackedTokensFromModels();
            for (const order of this.models["pos.order"].getAll()) {
                order.ensureSelfOrderLineChanges?.();
                if (order.isSynced && order.lines?.length) {
                    order.recomputeChanges();
                }
            }
            if (this._trackedOrderAccessTokens.size) {
                await this.getUserDataFromServer([...this._trackedOrderAccessTokens]);
            }
        }
    },

    requiresCustomerPhone() {
        return (
            this.config.self_ordering_mode === "mobile" &&
            this.config.self_order_require_customer_phone
        );
    },

    requiresPhoneOtp() {
        return this.requiresCustomerPhone() && this.config.self_order_require_phone_otp;
    },

    _restoreCustomerSession() {
        try {
            const stored = localStorage.getItem(CUSTOMER_SESSION_STORAGE_KEY);
            if (stored) {
                this.customerSession = JSON.parse(stored);
            }
        } catch {
            localStorage.removeItem(CUSTOMER_SESSION_STORAGE_KEY);
        }
    },

    _persistCustomerSession(session) {
        this.customerSession = session;
        if (session?.session_token) {
            localStorage.setItem(CUSTOMER_SESSION_STORAGE_KEY, JSON.stringify(session));
        } else {
            localStorage.removeItem(CUSTOMER_SESSION_STORAGE_KEY);
        }
    },

    getCustomerSession() {
        return this.customerSession;
    },

    hasVerifiedCustomer() {
        return Boolean(this.getCustomerSession()?.session_token);
    },

    clearCustomerSession() {
        this._persistCustomerSession(null);
        const order = this.currentOrder;
        if (order) {
            order.partner_id = false;
            order.mobile = false;
        }
    },

    applyCustomerToCurrentOrder(partnerRecord = null) {
        const order = this.currentOrder;
        const session = this.getCustomerSession();
        if (!order || !session?.partner_id) {
            return;
        }
        const partner =
            partnerRecord ||
            this.models["res.partner"].get(session.partner_id) ||
            this.models["res.partner"].find((entry) => entry.id === session.partner_id);
        if (partner) {
            order.partner_id = partner;
            order.mobile = partner.phone || session.phone;
        }
    },

    _applyCustomerSessionResult(result) {
        if (result?.partner) {
            this.models.connectNewData(result.partner);
        }
        this._persistCustomerSession({
            session_token: result.session_token,
            partner_id: result.partner_id,
            phone: result.phone,
            name: result.name,
        });
        const partner = this.models["res.partner"].get(result.partner_id);
        this.applyCustomerToCurrentOrder(partner);
    },

    async validateCustomerSession() {
        const session = this.getCustomerSession();
        if (!session?.session_token || !this.requiresCustomerPhone()) {
            return false;
        }
        try {
            const result = await rpc("/pos-self-order/customer/session", {
                access_token: this.access_token,
                customer_session_token: session.session_token,
            });
            this._applyCustomerSessionResult(result);
            return true;
        } catch {
            this.clearCustomerSession();
            return false;
        }
    },

    async sendCustomerOtp(phone, name = null) {
        return rpc("/pos-self-order/customer/send-otp", {
            access_token: this.access_token,
            phone,
            name,
        });
    },

    async verifyCustomerOtp(phone, code, name = null) {
        const result = await rpc("/pos-self-order/customer/verify-otp", {
            access_token: this.access_token,
            phone,
            code,
            name,
        });
        this._applyCustomerSessionResult(result);
        if (result?.debug_otp) {
            this.notification.add(_t("Debug OTP: %s", result.debug_otp), { type: "info" });
        }
        this.notification.add(_t("Phone number verified."), { type: "success" });
        return result;
    },

    async identifyCustomer(phone, name = null) {
        const result = await rpc("/pos-self-order/customer/identify", {
            access_token: this.access_token,
            phone,
            name,
        });
        this._applyCustomerSessionResult(result);
        this.notification.add(_t("Phone number saved."), { type: "success" });
        return result;
    },

    _restoreTrackedOrders() {
        try {
            let stored = localStorage.getItem(TRACKED_ORDERS_STORAGE_KEY);
            if (!stored) {
                stored = sessionStorage.getItem(TRACKED_ORDERS_STORAGE_KEY);
                if (stored) {
                    localStorage.setItem(TRACKED_ORDERS_STORAGE_KEY, stored);
                    sessionStorage.removeItem(TRACKED_ORDERS_STORAGE_KEY);
                }
            }
            if (!stored) {
                return;
            }
            for (const orderAccessToken of JSON.parse(stored)) {
                if (orderAccessToken) {
                    this._trackedOrderAccessTokens.add(orderAccessToken);
                }
            }
        } catch {
            localStorage.removeItem(TRACKED_ORDERS_STORAGE_KEY);
        }
    },

    _persistTrackedOrders() {
        localStorage.setItem(
            TRACKED_ORDERS_STORAGE_KEY,
            JSON.stringify([...this._trackedOrderAccessTokens])
        );
    },

    getTrackedOrderAccessTokens() {
        if (!(this._trackedOrderAccessTokens instanceof Set)) {
            this._trackedOrderAccessTokens = new Set();
        }
        return [...this._trackedOrderAccessTokens];
    },

    trackOrderRequest(orderAccessToken) {
        if (!orderAccessToken || !this.usesPaymentChoice()) {
            return;
        }
        this._trackedOrderAccessTokens.add(orderAccessToken);
        this._persistTrackedOrders();
        this.fetchOrderRequestStatus(orderAccessToken);
    },

    _syncTrackedTokensFromModels() {
        if (!this.usesPaymentChoice()) {
            return;
        }
        let changed = false;
        for (const order of this.models["pos.order"].filter(
            (entry) => entry.access_token && entry.isSynced
        )) {
            if (
                this.isOrderLockedForPayment(order) ||
                order.state === "paid" ||
                order.state === "done"
            ) {
                if (!this._trackedOrderAccessTokens.has(order.access_token)) {
                    this._trackedOrderAccessTokens.add(order.access_token);
                    changed = true;
                }
            }
        }
        if (changed) {
            this._persistTrackedOrders();
        }
    },

    async fetchAllOrderRequestStatuses() {
        const tokens = this.getTrackedOrderAccessTokens();
        if (!tokens.length || !this.usesPaymentChoice()) {
            return;
        }
        try {
            const results = await rpc("/pos-self-order/location-request-statuses", {
                access_token: this.access_token,
                order_access_tokens: tokens,
            });
            for (const [orderAccessToken, status] of Object.entries(results || {})) {
                this._applyOrderRequestStatus(orderAccessToken, {
                    state: status?.state,
                    name: status?.name,
                });
            }
        } catch {
            // Keep the last known statuses if polling fails.
        }
    },

    async refreshCustomerOrderHistory() {
        if (this.requiresCustomerPhone() && this.hasVerifiedCustomer()) {
            try {
                const data = await rpc("/pos-self-order/customer/order-history", {
                    access_token: this.access_token,
                    customer_session_token: this.getCustomerSession().session_token,
                });
                if (data?.statuses) {
                    for (const [orderAccessToken, status] of Object.entries(data.statuses)) {
                        this._applyOrderRequestStatus(orderAccessToken, status);
                        this.trackOrderRequest(orderAccessToken);
                    }
                }
                const { statuses, ...orderData } = data || {};
                if (orderData && Object.keys(orderData).length) {
                    const loaded = this.models.connectNewData(orderData);
                    this._finalizeOrdersFromConnect(loaded);
                    this.data.debouncedSynchronizeLocalDataInIndexedDB();
                }
            } catch (error) {
                if (
                    error instanceof RPCError &&
                    error.data?.name === "werkzeug.exceptions.Unauthorized"
                ) {
                    this.clearCustomerSession();
                } else {
                    this.handleErrorNotification(error);
                }
            }
            return;
        }

        if (!this.usesPaymentChoice()) {
            return;
        }
        this._syncTrackedTokensFromModels();
        const tokens = this.getTrackedOrderAccessTokens();
        if (tokens.length) {
            await this.getUserDataFromServer(tokens);
        }
        await this.fetchAllOrderRequestStatuses();
    },

    getHistoryOrders() {
        const session = this.getCustomerSession();
        if (this.requiresCustomerPhone() && session?.partner_id) {
            return this.models["pos.order"]
                .filter(
                    (order) =>
                        order.access_token &&
                        order.lines.length &&
                        order.partner_id?.id === session.partner_id
                )
                .sort((a, b) => (b.id || 0) - (a.id || 0));
        }

        const tracked = new Set(this.getTrackedOrderAccessTokens());
        return this.models["pos.order"]
            .filter((order) => {
                if (!order.access_token || !order.lines.length) {
                    return false;
                }
                if (!this.usesPaymentChoice() || !tracked.size) {
                    return true;
                }
                return tracked.has(order.access_token);
            })
            .sort((a, b) => (b.id || 0) - (a.id || 0));
    },

    async getUserDataFromServer(tokens = []) {
        if (!this.usesPaymentChoice()) {
            return super.getUserDataFromServer(...arguments);
        }

        const preservedTokens = new Set([
            ...this.getTrackedOrderAccessTokens(),
            ...tokens,
        ]);
        for (const order of this.models["pos.order"].filter((o) => this.isOrderLockedForPayment(o))) {
            preservedTokens.add(order.access_token);
        }

        const tableIdentifier = this.router.getTableIdentifier([]);
        const dbAccessToken = this.models["pos.order"]
            .filter(
                (order) =>
                    order.state === "draft" &&
                    order.isSynced &&
                    order.access_token &&
                    !this.isOrderLockedForPayment(order)
            )
            .map((order) => ({
                access_token: order.access_token,
                state: order.state,
                write_date: serializeDateTime(order.write_date.plus({ seconds: 1 })),
            }));

        const requestedTokens = [...preservedTokens].map((token) => ({
            access_token: token,
            write_date: "1970-01-01 00:00:00",
        }));

        const accessTokens = [
            ...new Map(
                [...dbAccessToken, ...requestedTokens].map((entry) => [entry.access_token, entry])
            ).values(),
        ];

        if (accessTokens.length === 0 && !tableIdentifier) {
            return;
        }

        try {
            const data = await rpc("/pos-self-order/get-user-data/", {
                access_token: this.access_token,
                order_access_tokens: accessTokens,
                table_identifier: tableIdentifier,
            });
            const result = this.models.connectNewData(data);
            this._finalizeOrdersFromConnect(result);
            const openOrder = result["pos.order"]?.find(
                (order) => order.state === "draft" && !this.isOrderLockedForPayment(order)
            );

            if (openOrder && this.router.activeSlot !== "confirmation") {
                this.selectedOrderUuid = openOrder.uuid;
                const lineCmd = [];
                for (const order of this.models["pos.order"].filter((o) => o.state === "draft")) {
                    if (
                        order.uuid !== openOrder.uuid &&
                        !this.isOrderLockedForPayment(order)
                    ) {
                        lineCmd.push(...order.lines);
                        order.delete();
                    }
                }
                if (lineCmd.length) {
                    openOrder.update({
                        lines: [["link", lineCmd]],
                    });
                    openOrder.recomputeChanges();
                }
            }
            this.data.debouncedSynchronizeLocalDataInIndexedDB();
        } catch (error) {
            this.handleErrorNotification(
                error,
                this.models["pos.order"].map((order) => order.access_token)
            );
        }
    },

    getOrderRequestStatus(orderAccessToken) {
        return (
            this.orderRequestStatuses[orderAccessToken] || {
                state: false,
                name: false,
                loaded: false,
            }
        );
    },

    _applyOrderRequestStatus(orderAccessToken, { state, name }) {
        if (!orderAccessToken || (state && !TRACKED_REQUEST_STATES.has(state))) {
            return;
        }

        const previousState = this.orderRequestStatuses[orderAccessToken]?.state;
        this.orderRequestStatuses = {
            ...this.orderRequestStatuses,
            [orderAccessToken]: {
                state: state || previousState || false,
                name: name || this.orderRequestStatuses[orderAccessToken]?.name || false,
                loaded: true,
            },
        };

        if (state) {
            this._notifyRequestStateListeners(orderAccessToken, state);
            if (state === "accepted" && previousState !== "accepted") {
                this.notification.add(_t("Your order has been confirmed!"), {
                    type: "success",
                    sticky: true,
                });
            } else if (state === "cancelled" && previousState !== "cancelled") {
                this.notification.add(_t("Your order has been cancelled."), {
                    type: "warning",
                    sticky: true,
                });
            }
        }
    },

    async fetchOrderRequestStatus(orderAccessToken) {
        if (!orderAccessToken || !this.usesPaymentChoice()) {
            return;
        }
        try {
            const result = await rpc("/pos-self-order/location-request-status", {
                access_token: this.access_token,
                order_access_token: orderAccessToken,
            });
            this._applyOrderRequestStatus(orderAccessToken, {
                state: result?.state,
                name: result?.name,
            });
        } catch {
            // Keep the last known status if polling fails.
        }
    },

    _startGlobalRequestStatusPolling() {
        clearInterval(this._globalRequestStatusPoll);
        this._globalRequestStatusPoll = setInterval(() => {
            for (const orderAccessToken of this._trackedOrderAccessTokens) {
                this.fetchOrderRequestStatus(orderAccessToken);
            }
        }, REQUEST_STATUS_POLL_MS);
    },

    _notifyRequestStateListeners(orderAccessToken, state) {
        for (const listener of this._requestStateListeners || []) {
            listener(orderAccessToken, state);
        }
    },

    onRequestStateUpdate(listener) {
        this._requestStateListeners.add(listener);
        return () => this._requestStateListeners.delete(listener);
    },

    usesPaymentChoice() {
        return (
            this.config.self_ordering_mode === "mobile" &&
            this.config.self_order_payment_choice_enabled
        );
    },

    _finalizeOrdersFromConnect(connectResult) {
        if (!connectResult) {
            return;
        }
        for (const order of connectResult["pos.order"] || []) {
            order.ensureSelfOrderLineChanges?.();
            if (order.isSynced && order.lines?.length) {
                order.recomputeChanges();
            }
        }
    },

    isOrderLockedForPayment(order = this.currentOrder) {
        if (!order || !this.usesPaymentChoice() || !order.isSynced) {
            return false;
        }

        const status = this.getOrderRequestStatus(order.access_token);
        if (status.loaded && status.state === "cancelled") {
            return false;
        }

        if (order.state === "paid") {
            return true;
        }

        order.ensureSelfOrderLineChanges?.();
        return order.state === "draft" && Object.keys(order.changes).length === 0;
    },

    getLatestSubmittedOrder() {
        return (
            this.models["pos.order"]
                .filter((order) => order.access_token && this.isOrderLockedForPayment(order))
                .sort((a, b) => (b.id || 0) - (a.id || 0))[0] || null
        );
    },

    startNewOrder() {
        this.selectedOrderUuid = null;
        const order = this.createNewOrder();
        this.selectedOrderUuid = order.uuid;
        return order;
    },

    createNewOrder() {
        const order = super.createNewOrder(...arguments);
        this.applyCustomerToCurrentOrder();
        return order;
    },

    get currentOrder() {
        const orderAvailable = (order) => {
            const isDraft = order.state === "draft";
            const isPaid = order.state === "paid";
            const isZeroAmount = order.amount_total === 0;
            const isKiosk = this.config.self_ordering_mode === "kiosk";

            const available =
                isDraft ||
                (isPaid && isZeroAmount && isKiosk) ||
                (isPaid && this.router.activeSlot === "confirmation");

            if (!available) {
                return false;
            }

            if (this.isOrderLockedForPayment(order)) {
                const slot = this.router.activeSlot;
                if (slot === "confirmation") {
                    return true;
                }
                if (slot === "cart" && this.selectedOrderUuid === order.uuid) {
                    return true;
                }
                return false;
            }

            return true;
        };

        const order = this.models["pos.order"].getBy("uuid", this.selectedOrderUuid);
        if (order && orderAvailable(order)) {
            return order;
        }

        const existingOrder = this.models["pos.order"].find((o) => orderAvailable(o));
        if (existingOrder) {
            this.selectedOrderUuid = existingOrder.uuid;
            return existingOrder;
        }

        return this.createNewOrder();
    },

    mustSyncOrderLevelFields() {
        const order = this.currentOrder;
        return (
            this.usesPaymentChoice() &&
            Boolean(
                order?.customer_payment_preference ||
                    order?.customer_location_captured ||
                    order?.customer_latitude ||
                    order?.customer_longitude
            )
        );
    },

    async sendDraftOrderToServer() {
        const order = this.currentOrder;
        const hasLineChanges = Object.keys(order.changes).length > 0;
        const hasOrderLevelFields = this.mustSyncOrderLevelFields();

        if (order.lines.length === 0) {
            return order;
        }

        if (!hasLineChanges && !hasOrderLevelFields) {
            return order;
        }

        if (hasLineChanges) {
            return super.sendDraftOrderToServer(...arguments);
        }

        try {
            order.setOrderPrices();
            const tableIdentifier = this.router.getTableIdentifier();
            let uuid = this.selectedOrderUuid;
            const data = await rpc(
                `/pos-self-order/process-order/${this.config.self_ordering_mode}`,
                {
                    order: order.serializeForORM(),
                    access_token: this.access_token,
                    table_identifier: tableIdentifier,
                }
            );
            const result = this.models.connectNewData(data);
            this._finalizeOrdersFromConnect(result);
            if (result["pos.order"][0].uuid !== this.selectedOrderUuid) {
                this.orderTakeAwayState[result["pos.order"][0].uuid] =
                    this.orderTakeAwayState[this.selectedOrderUuid];
                delete this.orderTakeAwayState[this.selectedOrderUuid];
                order.delete();
                uuid = result["pos.order"][0].uuid;
            }
            this.data.debouncedSynchronizeLocalDataInIndexedDB();

            if (this.config.self_ordering_pay_after === "each") {
                this.selectedOrderUuid = null;
            }

            order.recomputeChanges();
            return this.models["pos.order"].getBy("uuid", uuid);
        } catch (error) {
            const failedOrder = this.models["pos.order"].getBy("uuid", this.selectedOrderUuid);
            this.handleErrorNotification(error, [failedOrder?.access_token]);
            return false;
        }
    },

    async confirmOrder() {
        if (this.requiresCustomerPhone() && !this.hasVerifiedCustomer()) {
            this.notification.add(_t("Please verify your phone number before ordering."), {
                type: "warning",
            });
            return;
        }
        this.applyCustomerToCurrentOrder();

        if (!this.usesPaymentChoice()) {
            return super.confirmOrder(...arguments);
        }

        const order = this.currentOrder;
        if (this.isOrderLockedForPayment(order)) {
            this.confirmationPage("order", this.config.self_ordering_mode, order.access_token);
            return;
        }

        const preference = order.customer_payment_preference;
        const device = this.config.self_ordering_mode;

        if (!preference) {
            this.notification.add(_t("Please choose how you want to pay."), { type: "warning" });
            return;
        }

        const savedOrder = await this.sendDraftOrderToServer();
        if (!savedOrder) {
            return;
        }

        if (preference === "cash_on_delivery") {
            this.trackOrderRequest(savedOrder.access_token);
            this.notification.add(
                _t(
                    "Your order was submitted successfully. Please wait until it is confirmed."
                ),
                { type: "success" }
            );
            this.confirmationPage("order", device, savedOrder.access_token);
            return;
        }

        if (preference === "online_card") {
            const onlinePaymentMethod = this.config.self_order_online_payment_method_id;
            if (!onlinePaymentMethod) {
                this.notification.add(
                    _t("Online card payment is not configured for this store."),
                    { type: "danger" }
                );
                return;
            }
            const onlinePaymentUrl = this.getOnlinePaymentUrl(savedOrder, true);
            window.open(onlinePaymentUrl, "_self");
            return;
        }

        return super.confirmOrder(...arguments);
    },
});
