/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { uuidv4 } from "@point_of_sale/utils";
import { rpc, ConnectionLostError } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { CustomCakeFormPopup } from "@pos_custom_cake/app/screens/product_screen/control_buttons/cake_button/custom_cake_form_popup";
import { CakeOrdersListPopup } from "@pos_custom_cake/app/screens/product_screen/control_buttons/cake_button/cake_orders_list_popup";
import { serverErrorMessage } from "@pos_local_sql_backup/app/pos_store_patch";
import { getLocalCake, negativeIdFromUuid } from "@pos_local_sql_backup_cake/app/local_cake_store";
import { readCakeConfigCache } from "@pos_local_sql_backup_cake/app/cake_config_cache";
import { removeCakeOrderFromCache } from "@pos_local_sql_backup_cake/app/cake_orders_cache";

function isOfflineError(error) {
    if (!error) {
        return false;
    }
    if (error instanceof ConnectionLostError) {
        return true;
    }
    const msg = String(error?.message || error?.data?.message || "").toLowerCase();
    return (
        msg.includes("connection lost") ||
        msg.includes("failed to fetch") ||
        msg.includes("networkerror") ||
        msg.includes("offline") ||
        error?.name === "ConnectionLostError"
    );
}

patch(ControlButtons.prototype, {
    async onClickCustomCake() {
        if (!this.isCustomCakeEnabled()) {
            this.notification.add(_t("Custom Cake is not enabled on this POS."), {
                type: "warning",
            });
            return;
        }

        return this._runWithCakeBackup("create", async () => {
            const popupResult = await makeAwaitable(this.dialog, CustomCakeFormPopup, {
                pos: this.pos,
            });
            if (!popupResult) {
                return;
            }

            const localUuid = uuidv4();
            this.pos._cakeBackupLocalUuid = localUuid;
            this.pos._cakeBackupPrices = popupResult.prices || {};
            this.pos._cakeBackupPartner = popupResult.partner || null;

            const payload = {
                ...popupResult.payload,
                local_uuid: localUuid,
            };

            try {
                const result = await rpc("/pos/custom_cake/create_order", payload);
                this._confirmCakeBackupFromServer(
                    result,
                    popupResult.action === "pay_later" ? "cake_pay_later" : "cake_created",
                    localUuid
                );

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
                    const order = this._getCurrentOrder();
                    if (order) {
                        order.pos_cake_local_uuid = localUuid;
                    }
                    const moLabel = result?.production_name
                        ? _t("MO: %s", result.production_name)
                        : "";
                    this.notification.add(
                        _t("Custom cake added: %s %s", result?.name || "", moLabel).trim(),
                        { type: "success" }
                    );
                }
            } catch (error) {
                if (!isOfflineError(error) && !readCakeConfigCache(this.pos)) {
                    const msg =
                        error?.data?.message ||
                        error?.message ||
                        _t("Failed to create custom cake order.");
                    this.notification.add(msg, { type: "danger" });
                    this.pos.recordLocalBackupEvent("cake_failed", {
                        failed_action: "create",
                        error: serverErrorMessage(error) || String(error),
                    });
                    return;
                }

                // Offline (or unreachable): keep local cake and continue cashier flow.
                const local = this.pos.saveLocalCakeFromCreate(payload, localUuid, {
                    partner_name: popupResult.partner?.name || "",
                    partner_phone: popupResult.partner?.phone || "",
                    prices: popupResult.prices || {},
                    state: "waiting",
                    pending_action: "create",
                });
                const localResult = this.pos.localCakeAsPosResult(localUuid);
                this.pos.recordLocalBackupEvent(
                    popupResult.action === "pay_later" ? "cake_pay_later" : "cake_created",
                    {
                        local_only: true,
                        cake: {
                            id: negativeIdFromUuid(localUuid),
                            local_uuid: localUuid,
                            reference: local?.name || `Local ${String(localUuid).slice(0, 8)}`,
                            partner_name: local?.partner_name,
                            partner_phone: local?.partner_phone,
                            product_name: local?.product_name,
                            pieces: local?.pieces,
                            sugar_paste: local?.sugar_paste,
                            note: local?.note,
                            cake_base_cost: local?.cake_base_cost,
                            total_components_cost: local?.total_components_cost,
                            price_before_tax: local?.price_before_tax,
                            tax_amount: local?.tax_amount,
                            final_price: local?.final_price,
                            size_name: local?.size_name,
                        },
                        form: {
                            phone: local?.partner_phone,
                            size_name: local?.size_name,
                            components: local?.form_components || [],
                        },
                        pos_order_uuid: this._getCurrentOrder?.()?.uuid || null,
                    }
                );
                this._cakeCopyRecorded = true;

                if (popupResult.action === "pay_later") {
                    this.notification.add(
                        _t(
                            "Cake saved on this register (pay later). It will sync when the connection is back. Manufacturing order is created on sync."
                        ),
                        { type: "warning" }
                    );
                    this._showPayLaterReceipt(localResult, popupResult.partner);
                    this.pos.syncLocalCakes();
                    return;
                }

                const added = await this._addCakeProductToOrder({
                    result: localResult,
                    partnerId: popupResult.partner?.id,
                });
                if (added) {
                    const order = this._getCurrentOrder();
                    if (order) {
                        order.pos_cake_local_uuid = localUuid;
                        this.pos.markLocalCakeLoaded(localUuid, order.uuid);
                        // Refresh helper cake row with the POS ticket link.
                        this.pos.recordLocalBackupEvent("cake_created", {
                            local_only: true,
                            cake: {
                                id: negativeIdFromUuid(localUuid),
                                local_uuid: localUuid,
                                reference: local?.name || `Local ${String(localUuid).slice(0, 8)}`,
                                partner_name: local?.partner_name,
                                partner_phone: local?.partner_phone,
                                product_name: local?.product_name,
                                pieces: local?.pieces,
                                sugar_paste: local?.sugar_paste,
                                note: local?.note,
                                cake_base_cost: local?.cake_base_cost,
                                total_components_cost: local?.total_components_cost,
                                price_before_tax: local?.price_before_tax,
                                tax_amount: local?.tax_amount,
                                final_price: local?.final_price,
                                size_name: local?.size_name,
                            },
                            form: {
                                phone: local?.partner_phone,
                                size_name: local?.size_name,
                                components: local?.form_components || [],
                            },
                            pos_order_uuid: order.uuid,
                        });
                    }
                    this.notification.add(
                        _t(
                            "Custom cake saved on this register. It will sync when the connection is back. Manufacturing order is created on sync."
                        ),
                        { type: "warning" }
                    );
                }
                this.pos.syncLocalCakes();
            }
        });
    },

    async onClickCakeOrders() {
        if (!this.isCustomCakeEnabled()) {
            this.notification.add(_t("Custom Cake is not enabled on this POS."), {
                type: "warning",
            });
            return;
        }

        return this._runWithCakeBackup("load", async () => {
            const popupResult = await makeAwaitable(this.dialog, CakeOrdersListPopup, {
                pos: this.pos,
            });
            if (!popupResult?.order) {
                return;
            }

            const selected = popupResult.order;
            const localUuid = selected.local_uuid || null;
            const isLocal =
                selected.is_local ||
                (localUuid && !(selected.id > 0)) ||
                Number(selected.id) < 0;

            if (isLocal && localUuid) {
                const localResult = this.pos.localCakeAsPosResult(localUuid);
                if (!localResult?.product_id) {
                    this.notification.add(
                        _t("Local cake product is not available in this POS."),
                        { type: "danger" }
                    );
                    return;
                }
                // Ensure create syncs before payment when possible.
                if (!getLocalCake(this.pos, localUuid)?.server_id) {
                    this.pos.syncLocalCakes();
                }
                const synced = getLocalCake(this.pos, localUuid);
                const result = synced?.server_id
                    ? this.pos.localCakeAsPosResult(localUuid)
                    : localResult;
                const added = await this._addCakeProductToOrder({
                    result,
                    partnerId: result.partner_id,
                });
                if (added) {
                    const order = this._getCurrentOrder();
                    if (order) {
                        order.pos_cake_local_uuid = localUuid;
                        this.pos.markLocalCakeLoaded(localUuid, order.uuid);
                    }
                    this.pos.recordLocalBackupEvent("cake_loaded", {
                        local_only: !synced?.server_id,
                        cake: {
                            id: result.id > 0 ? result.id : null,
                            local_uuid: localUuid,
                            reference: result.name,
                            partner_name: result.partner_name,
                            product_name: result.product_name,
                            pieces: result.pieces,
                            final_price: result.final_price,
                        },
                        pos_order_uuid: order?.uuid || null,
                    });
                    this.notification.add(
                        synced?.server_id
                            ? _t("Cake order loaded: %s", result.name || "")
                            : _t(
                                  "Local cake loaded. It will finish syncing when the connection is back."
                              ),
                        { type: synced?.server_id ? "success" : "warning" }
                    );
                }
                return;
            }

            try {
                const result = await rpc("/pos/custom_cake/get_order", {
                    order_id: selected.id,
                });
                const added = await this._addCakeProductToOrder({
                    result,
                    partnerId: result.partner_id,
                });
                if (added) {
                    removeCakeOrderFromCache(this.pos, result.id);
                    this.pos.recordLocalBackupEvent("cake_loaded", {
                        cake: {
                            id: result.id,
                            reference: result.name,
                            partner_name: result.partner_name,
                            product_name: result.product_name,
                            pieces: result.pieces,
                            final_price: result.final_price,
                            sugar_paste: result.sugar_paste,
                            note: result.note,
                            cake_base_cost: result.cake_base_cost,
                            total_components_cost: result.total_components_cost,
                            price_before_tax: result.price_before_tax,
                            tax_amount: result.tax_amount,
                            production_name: result.production_name,
                        },
                        pos_order_uuid: this._getCurrentOrder?.()?.uuid || null,
                    });
                    this.notification.add(
                        _t("Cake order loaded: %s", result?.name || ""),
                        { type: "success" }
                    );
                }
            } catch (error) {
                // Cached server cake: use cached row fields if get_order fails offline.
                if (selected.from_server_cache || isOfflineError(error)) {
                    const cachedResult = {
                        id: selected.id,
                        name: selected.name,
                        partner_id: selected.partner_id || null,
                        partner_name: selected.partner_name,
                        product_id: selected.product_id,
                        product_name: selected.product_name,
                        pieces: selected.pieces,
                        final_price: selected.final_price,
                        price_before_tax: selected.price_before_tax || selected.final_price,
                        tax_amount: selected.tax_amount || 0,
                        note: selected.note || "",
                        sugar_paste: selected.sugar_paste || false,
                        cake_base_cost: selected.cake_base_cost || 0,
                        total_components_cost: selected.total_components_cost || 0,
                        production_id: false,
                        production_name: false,
                    };
                    if (!cachedResult.product_id) {
                        this.notification.add(
                            _t(
                                "Cannot load this cake offline: product details were not cached. Reopen POS online once."
                            ),
                            { type: "danger" }
                        );
                        return;
                    }
                    const added = await this._addCakeProductToOrder({
                        result: cachedResult,
                        partnerId: cachedResult.partner_id,
                    });
                    if (added) {
                        this.pos.recordLocalBackupEvent("cake_loaded", {
                            local_only: true,
                            cake: {
                                id: cachedResult.id,
                                reference: cachedResult.name,
                                partner_name: cachedResult.partner_name,
                                product_name: cachedResult.product_name,
                                pieces: cachedResult.pieces,
                                final_price: cachedResult.final_price,
                            },
                            pos_order_uuid: this._getCurrentOrder?.()?.uuid || null,
                        });
                        this.notification.add(
                            _t("Cake loaded from cache (offline): %s", cachedResult.name || ""),
                            { type: "warning" }
                        );
                    }
                    return;
                }
                const msg =
                    error?.data?.message || error?.message || _t("Failed to load cake order.");
                this.notification.add(msg, { type: "danger" });
            }
        });
    },
});
