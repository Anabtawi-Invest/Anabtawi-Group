/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PledgeListPopup } from "@pos_pledge_order/js/pledge_list_popup";

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

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.watchPledgeReturns();
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
                } catch (error) {
                    console.warn("[LOCAL_BACKUP] Could not record the pledge return:", error);
                }
            },
            (error) => {
                try {
                    this.recordLocalBackupPledgeReturnFailure(selection, error);
                } catch (recordError) {
                    console.warn("[LOCAL_BACKUP] Could not record the failed pledge return:", recordError);
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
});

patch(PledgeListPopup.prototype, {
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
        return super.confirmReturn(...arguments);
    },
});
