/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { CompleteAdvanceOrderPopup } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/complete_advance_order_popup";
import { localAdvancesForComplete } from "@pos_local_sql_backup_advance/app/local_advance_store";
import { readCompletableAdvanceCache } from "@pos_local_sql_backup_advance/app/complete_advance_cache";

patch(CompleteAdvanceOrderPopup.prototype, {
    async _loadAdvanceOrders() {
        await super._loadAdvanceOrders(...arguments);
        const serverOrders = this.state.advance_orders || [];
        const usedServer = Boolean(serverOrders.length);
        const cachedOrders = usedServer ? [] : readCompletableAdvanceCache(this.props.pos);
        const localOrders = localAdvancesForComplete(this.props.pos);
        const byId = new Map();
        for (const order of [...cachedOrders, ...localOrders, ...serverOrders]) {
            if (order?.id == null) {
                continue;
            }
            const existing = byId.get(order.id);
            if (!existing) {
                byId.set(order.id, order);
                continue;
            }
            // Prefer live server rows, then local pending rows, then cache.
            if (usedServer && serverOrders.some((row) => row.id === order.id)) {
                byId.set(order.id, { ...existing, ...order, from_server_cache: false });
            } else if (order.is_local || order.local_uuid) {
                byId.set(order.id, { ...existing, ...order });
            }
        }
        this.state.advance_orders = [...byId.values()];
        if (!usedServer && this.state.advance_orders.length) {
            this.notification.add(
                _t(
                    "Showing advances saved on this register (local creates and the last online list). Completion stays local until Odoo is reached."
                ),
                { type: "warning" }
            );
        }
    },

    async _loadOrderDetail(orderId) {
        const selected = this.state.advance_orders.find((order) => order.id === orderId);
        if (selected?.is_local || orderId < 0 || selected?.from_server_cache) {
            const lines = selected.lines || [];
            this.state.detail_lines = lines.map((line, index) => ({
                id: line.id || index + 1,
                product_id: Array.isArray(line.product_id)
                    ? line.product_id
                    : line.product_id
                      ? [line.product_id, line.product_name || line.product_id_name || ""]
                      : false,
                product_qty: line.product_qty ?? line.qty ?? 0,
                price_unit: line.price_unit ?? 0,
                discount: line.discount ?? 0,
                price_subtotal_incl: line.price_subtotal_incl ?? line.subtotal ?? 0,
                display_type: false,
                sequence: line.sequence || index + 1,
            }));
            return;
        }
        return super._loadOrderDetail(...arguments);
    },

    confirm() {
        if (!this.state.selected_order_id) {
            return super.confirm(...arguments);
        }
        const selected = this.selectedOrder;
        const useLocalPath =
            selected?.is_local ||
            selected?.from_server_cache ||
            this.state.selected_order_id < 0;
        if (!useLocalPath) {
            return super.confirm(...arguments);
        }
        if (!this.state.selected_payment_method_id) {
            this.notification.add(
                this._tr("Please select a payment method.", "يرجى اختيار طريقة دفع."),
                { type: "warning" }
            );
            return;
        }
        if (this.state.amount_tendered < this.selectedRemainingAmount) {
            this.notification.add(
                this._tr(
                    "Amount tendered cannot be less than remaining amount.",
                    "لا يمكن أن يكون المبلغ المستلم أقل من المبلغ المتبقي."
                ),
                { type: "warning" }
            );
            return;
        }
        const selectedPm = this.state.payment_methods.find(
            (pm) => pm.id === this.state.selected_payment_method_id
        );
        this.props.getPayload({
            advance_order_id: this.state.selected_order_id,
            local_uuid: selected.local_uuid || null,
            is_local: Boolean(selected.is_local || this.state.selected_order_id < 0),
            from_server_cache: Boolean(selected.from_server_cache),
            reference: selected.name || "",
            partner_name: selected.partner_id?.[1] || "",
            partner_phone: selected.partner_phone || "",
            amount_total: selected.amount_total,
            advance_amount: selected.advance_amount,
            amount_remaining: selected.amount_remaining,
            lines: selected.lines || [],
            payment_method_id: this.state.selected_payment_method_id,
            payment_method_name: selectedPm?.name || "",
            amount_tendered: this.state.amount_tendered,
            change_amount: this.remainingChangeAmount,
        });
        this.props.close();
    },
});
