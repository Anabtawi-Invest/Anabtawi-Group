/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { uuidv4 } from "@point_of_sale/utils";
import { _t } from "@web/core/l10n/translation";
import { ConnectionLostError } from "@web/core/network/rpc";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PledgeListPopup } from "@pos_pledge_order/js/pledge_list_popup";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { localPledgesForReturn } from "@pos_local_sql_backup_advance/app/local_advance_store";
import {
    readActivePledgeCache,
    removeActivePledgesFromCache,
} from "@pos_local_sql_backup_advance/app/pledge_return_cache";

const PLEDGE_MODEL = "pos.advance.order.pledge";
const RETURN_METHOD = "action_return_pledges";

function toNumber(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
}

function refundOrdersFromResult(result) {
    if (!result || typeof result !== "object") {
        return [];
    }
    if (Array.isArray(result.refund_orders)) {
        return result.refund_orders;
    }
    return result.refund_order_name || result.refund_order_id ? [result] : [];
}

function pendingPledgeReturnKey(pos) {
    return `pos_pending_pledge_returns_${odoo.info?.db || ""}_${pos?.config?.id || 0}`;
}

function readPendingPledgeReturns(pos) {
    try {
        const list = JSON.parse(localStorage.getItem(pendingPledgeReturnKey(pos)) || "[]");
        return Array.isArray(list) ? list : [];
    } catch {
        return [];
    }
}

function writePendingPledgeReturns(pos, rows) {
    try {
        localStorage.setItem(pendingPledgeReturnKey(pos), JSON.stringify(rows || []));
    } catch (error) {
        console.warn("[LOCAL_BACKUP] Could not save pending pledge returns:", error);
    }
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.watchPledgeReturns();
        this.syncPendingPledgeReturns();
        return result;
    },

    /**
     * The Return Pledge button calls the ORM service directly. Its class lives in a
     * different file depending on the Odoo version, so the service object is
     * wrapped here instead of patching the class.
     */
    watchPledgeReturns() {
        const orm = this.env?.services?.orm;
        if (!orm || orm.localBackupPledgeWatch) {
            return;
        }
        const store = this;
        const originalCall = orm.call;
        orm.call = function (model, method, args = []) {
            const promise = originalCall.apply(this, arguments);
            if (model === PLEDGE_MODEL && method === RETURN_METHOD && store.isLocalBackupEnabled) {
                store.observePledgeReturn(Array.isArray(args[0]) ? args[0] : [], promise);
            }
            return promise;
        };
        orm.localBackupPledgeWatch = true;
    },

    // Observe only: the caller still receives the original promise and its error.
    observePledgeReturn(pledgeIds, promise) {
        const selection = this.takePledgeReturnSelection(pledgeIds);
        Promise.resolve(promise).then(
            (result) => {
                try {
                    this.recordLocalBackupPledgeReturn(selection, result);
                    removeActivePledgesFromCache(this, pledgeIds);
                    this.refreshActivePledgeCache?.();
                } catch (error) {
                    console.warn("[LOCAL_BACKUP] Could not record the pledge return:", error);
                }
            },
            (error) => {
                try {
                    this.recordLocalBackupPledgeReturnFailure(selection, error);
                } catch (recordError) {
                    console.warn(
                        "[LOCAL_BACKUP] Could not record the failed pledge return:",
                        recordError
                    );
                }
            }
        );
    },

    rememberPledgeReturnSelection(selection) {
        this.pendingPledgeReturnSelection = selection;
    },

    takePledgeReturnSelection(pledgeIds) {
        const selection = this.pendingPledgeReturnSelection;
        this.pendingPledgeReturnSelection = null;
        const wanted = new Set(pledgeIds);
        if (!selection || !selection.pledges.some((pledge) => wanted.has(pledge.id))) {
            return { pledges: pledgeIds.map((id) => ({ id })) };
        }
        return selection;
    },

    recordLocalBackupPledgeReturn(selection, result) {
        const refundOrders = refundOrdersFromResult(result);
        this.recordLocalBackupEvent("pledge_returned", {
            partner_name: selection.partner_name || "",
            partner_phone: selection.partner_phone || "",
            payment_method_name:
                refundOrders[0]?.payment_method_name || selection.payment_method_name || "",
            total_amount: refundOrders.length
                ? refundOrders.reduce((sum, order) => sum + toNumber(order.amount), 0)
                : toNumber(selection.total_amount),
            pledges: selection.pledges,
            refund_orders: refundOrders.map((order) => ({
                refund_order_id: order.refund_order_id || null,
                refund_order_name: order.refund_order_name || "",
                origin_order_name: order.origin_order_name || "",
                pledge_ids: order.pledge_ids || [],
                payment_method_name: order.payment_method_name || "",
                amount: toNumber(order.amount),
            })),
            return_move_name: result?.return_move_name || "",
            raw: { result },
        });
    },

    recordLocalBackupPledgeReturnFailure(selection, error) {
        this.recordLocalBackupEvent("pledge_return_failed", {
            partner_name: selection.partner_name || "",
            partner_phone: selection.partner_phone || "",
            payment_method_name: selection.payment_method_name || "",
            total_amount: toNumber(selection.total_amount),
            pledges: selection.pledges,
            error: error?.data?.message || error?.message || String(error),
        });
    },

    queueLocalPledgeReturn(selection) {
        const serverPledges = (selection.pledges || []).filter(
            (pledge) => pledge.id > 0 && !pledge.is_local
        );
        const localPledges = (selection.pledges || []).filter(
            (pledge) => pledge.is_local || pledge.id < 0
        );
        if (localPledges.length) {
            this.markLocalPledgesReturned(localPledges);
        }
        if (serverPledges.length) {
            const row = {
                local_uuid: uuidv4(),
                pledge_ids: serverPledges.map((pledge) => pledge.id),
                pledges: serverPledges,
                payment_method_id: selection.payment_method_id,
                payment_method_name: selection.payment_method_name || "",
                partner_name: selection.partner_name || "",
                partner_phone: selection.partner_phone || "",
                total_amount: toNumber(selection.total_amount),
                created_at: new Date().toISOString(),
            };
            writePendingPledgeReturns(this, [...readPendingPledgeReturns(this), row]);
            removeActivePledgesFromCache(
                this,
                serverPledges.map((pledge) => pledge.id)
            );
            this.recordLocalBackupEvent("pledge_returned", {
                local_only: true,
                partner_name: row.partner_name,
                partner_phone: row.partner_phone,
                payment_method_name: row.payment_method_name,
                total_amount: row.total_amount,
                pledges: serverPledges.map((pledge) => ({
                    id: pledge.id,
                    reference: pledge.name || "",
                    product_name: pledge.product_id?.[1] || "",
                    qty: toNumber(pledge.pledge_qty),
                    unit_amount: toNumber(pledge.pledge_amount_unit),
                    amount: toNumber(pledge.pledge_subtotal ?? pledge.pledge_amount),
                })),
            });
        } else if (localPledges.length) {
            this.recordLocalBackupEvent("pledge_returned", {
                local_only: true,
                partner_name: selection.partner_name || "",
                partner_phone: selection.partner_phone || "",
                payment_method_name: selection.payment_method_name || "",
                total_amount: toNumber(selection.total_amount),
                pledges: localPledges.map((pledge) => ({
                    id: pledge.id,
                    local_uuid: pledge.local_uuid,
                    reference: pledge.name || "",
                    product_name: pledge.product_id?.[1] || "",
                    qty: toNumber(pledge.pledge_qty),
                    unit_amount: toNumber(pledge.pledge_amount_unit),
                    amount: toNumber(pledge.pledge_subtotal ?? pledge.pledge_amount),
                })),
            });
        }
        this.syncPendingPledgeReturns();
    },

    async syncPendingPledgeReturns() {
        if (this._pendingPledgeReturnSyncing) {
            return;
        }
        const pending = readPendingPledgeReturns(this);
        if (!pending.length) {
            return;
        }
        const orm = this.env?.services?.orm || this.data?.orm;
        if (!orm) {
            return;
        }
        this._pendingPledgeReturnSyncing = true;
        const remaining = [];
        try {
            for (const row of pending) {
                try {
                    const result = await orm.call(
                        PLEDGE_MODEL,
                        RETURN_METHOD,
                        [row.pledge_ids],
                        {
                            pos_payment_method_id: row.payment_method_id,
                            pos_session_id: this.session?.id || false,
                        }
                    );
                    this.recordLocalBackupPledgeReturn(
                        {
                            partner_name: row.partner_name,
                            partner_phone: row.partner_phone,
                            payment_method_name: row.payment_method_name,
                            total_amount: row.total_amount,
                            pledges: row.pledges,
                        },
                        result
                    );
                    this.refreshActivePledgeCache?.();
                } catch (error) {
                    console.warn("[LOCAL_BACKUP] Could not sync pledge return:", error);
                    remaining.push(row);
                }
            }
            writePendingPledgeReturns(this, remaining);
        } finally {
            this._pendingPledgeReturnSyncing = false;
        }
    },
});

patch(PledgeListPopup.prototype, {
    async _loadPledges() {
        await super._loadPledges(...arguments);
        const serverPledges = this.state.pledges || [];
        const usedServer = Boolean(serverPledges.length);
        const partnerId = this.props.partnerId || null;
        const cached = usedServer
            ? []
            : readActivePledgeCache(this.pos).filter(
                  (pledge) => !partnerId || pledge.partner_id?.[0] === partnerId
              );
        const localPledges = localPledgesForReturn(this.pos, partnerId);
        const byId = new Map();
        for (const pledge of [...cached, ...localPledges, ...serverPledges]) {
            if (pledge?.id == null) {
                continue;
            }
            const existing = byId.get(pledge.id);
            if (!existing) {
                byId.set(pledge.id, pledge);
                continue;
            }
            if (usedServer && serverPledges.some((row) => row.id === pledge.id)) {
                byId.set(pledge.id, { ...existing, ...pledge, from_server_cache: false });
            } else if (pledge.is_local || pledge.local_uuid) {
                byId.set(pledge.id, { ...existing, ...pledge });
            }
        }
        this.state.pledges = [...byId.values()];
        if (!usedServer && this.state.pledges.length) {
            this.notification.add(
                _t(
                    "Showing pledges saved on this register (local creates and the last online list). Return stays local until Odoo is reached."
                ),
                { type: "warning" }
            );
        }
    },

    async showPledgeDetails(pledge) {
        if (pledge?.is_local || pledge?.from_server_cache || pledge?.id < 0) {
            this.state.selectedPledgeDetails = {
                ...pledge,
                name: pledge.name || _t("POS Pledge"),
                pledge_amount: pledge.pledge_subtotal || pledge.pledge_amount || 0,
                employee_amount: 0,
                delivery_amount: 0,
                case_type: "case2",
                products: pledge.product_id
                    ? [
                          {
                              id: pledge.product_id[0],
                              name: pledge.product_id[1],
                              qty: pledge.pledge_qty || 1,
                          },
                      ]
                    : [],
            };
            return;
        }
        return super.showPledgeDetails(...arguments);
    },

    confirmReturn() {
        if (this.hasSelectedPledges && this.state.selected_payment_method_id) {
            const pledges = this.selectedPledges;
            const paymentMethod = this.state.payment_methods.find(
                (pm) => pm.id === this.state.selected_payment_method_id
            );
            this.pos.rememberPledgeReturnSelection({
                partner_name: pledges[0]?.partner_id?.[1] || "",
                partner_phone: pledges[0]?.partner_phone || "",
                payment_method_name: paymentMethod?.name || "",
                total_amount: this.selectedReturnTotal,
                pledges: pledges.map((pledge) => ({
                    id: pledge.id,
                    local_uuid: pledge.local_uuid || null,
                    local_pledge_key: pledge.local_pledge_key || null,
                    is_local: Boolean(pledge.is_local || pledge.id < 0),
                    from_server_cache: Boolean(pledge.from_server_cache),
                    reference: pledge.name || "",
                    product_name: pledge.product_id?.[1] || "",
                    qty: toNumber(pledge.pledge_qty),
                    unit_amount: toNumber(pledge.pledge_amount_unit),
                    amount: toNumber(pledge.pledge_subtotal ?? pledge.pledge_amount),
                    employee_name: pledge.employee_name || "",
                    created: pledge.create_date || "",
                })),
            });
        }
        const selected = this.selectedPledges || [];
        const useLocalPath = selected.some(
            (pledge) => pledge.is_local || pledge.from_server_cache || pledge.id < 0
        );
        if (useLocalPath && this.hasSelectedPledges && this.state.selected_payment_method_id) {
            const selectedPm = this.state.payment_methods.find(
                (pm) => pm.id === this.state.selected_payment_method_id
            );
            this.props.getPayload({
                pledge_ids: [...this.state.selectedPledgeIds],
                pledges: this.selectedPledges,
                payment_method_id: this.state.selected_payment_method_id,
                payment_method_name: selectedPm?.name || "",
                total_amount: this.selectedReturnTotal,
                is_local: selected.some((pledge) => pledge.is_local || pledge.id < 0),
                from_server_cache: selected.some((pledge) => pledge.from_server_cache),
                use_local_path: true,
            });
            this.props.close();
            return;
        }
        return super.confirmReturn(...arguments);
    },
});

patch(ControlButtons.prototype, {
    async onClickReturnPledge() {
        try {
            const partner = await makeAwaitable(this.dialog, PartnerList, {});
            if (!partner) {
                return;
            }
            const selection = await makeAwaitable(this.dialog, PledgeListPopup, {
                partnerId: partner.id,
            });
            if (!selection || !selection.pledge_ids?.length) {
                return;
            }
            const queueLocal = () => {
                this.pos.queueLocalPledgeReturn({
                    ...selection,
                    partner_name: partner.name || "",
                    partner_phone: partner.phone || partner.mobile || "",
                });
                this.notification.add(
                    _t(
                        "Pledge return saved on this register. It will sync when the connection is back."
                    ),
                    { type: "warning" }
                );
            };
            if (selection.use_local_path) {
                queueLocal();
                return;
            }
            try {
                const result = await this.env.services.orm.call(
                    PLEDGE_MODEL,
                    RETURN_METHOD,
                    [selection.pledge_ids],
                    {
                        pos_payment_method_id: selection.payment_method_id,
                        pos_session_id: this.pos.session?.id || false,
                    }
                );
                const pledgeCount = selection.pledge_ids.length;
                const batchCount =
                    result?.count ||
                    (result?.return_move_name || result?.refund_order_name ? 1 : 0);
                if (result?.return_via === "pos_refund" || result?.refund_order_name) {
                    this.notification.add(
                        _t(
                            "%s pledge(s) returned via POS refund order %s.",
                            pledgeCount,
                            result.refund_order_name || ""
                        ),
                        { type: "success" }
                    );
                } else if (batchCount > 1) {
                    this.notification.add(
                        _t("%s pledge(s) returned. Reversal entries created.", pledgeCount),
                        { type: "success" }
                    );
                } else {
                    this.notification.add(
                        _t(
                            "%s pledge(s) returned successfully. Reversal entry created.",
                            pledgeCount
                        ),
                        { type: "success" }
                    );
                }
            } catch (error) {
                if (error instanceof ConnectionLostError || navigator.onLine === false) {
                    queueLocal();
                    return;
                }
                throw error;
            }
        } catch (error) {
            console.error("[PLEDGE] Error returning pledge:", error);
            this.notification.add(
                error.message || error.data?.message || _t("Failed to return pledge"),
                { type: "danger" }
            );
        }
    },
});
