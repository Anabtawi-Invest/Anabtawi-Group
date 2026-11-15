/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { RefundAdvanceOrderPopup } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/refund_advance_order_popup";
import { localAdvancesForRefund } from "@pos_local_sql_backup_advance/app/local_advance_store";
import { readRefundableAdvanceCache } from "@pos_local_sql_backup_advance/app/refund_advance_cache";

patch(RefundAdvanceOrderPopup.prototype, {
    async _loadAdvanceOrders() {
        await super._loadAdvanceOrders(...arguments);
        const serverOrders = this.state.advance_orders || [];
        const usedServer = Boolean(serverOrders.length);
        const cachedOrders = usedServer ? [] : readRefundableAdvanceCache(this.props.pos);
        const localOrders = localAdvancesForRefund(this.props.pos);
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
                    "Showing advances saved on this register (local creates and the last online list). Refund stays local until Odoo is reached."
                ),
                { type: "warning" }
            );
        }
    },

    confirm() {
        if (!this.state.selected_order_id) {
            return super.confirm(...arguments);
        }
        const selected = this.state.advance_orders.find(
            (order) => order.id === this.state.selected_order_id
        );
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
        const selectedPm = this.state.payment_methods.find(
            (pm) => pm.id === this.state.selected_payment_method_id
        );
        this.props.getPayload({
            advance_order_id: this.state.selected_order_id,
            local_uuid: selected.local_uuid || null,
            is_local: Boolean(selected.is_local || this.state.selected_order_id < 0),
            from_server_cache: Boolean(selected.from_server_cache),
            advance_amount: Number(selected?.advance_amount ?? 0),
            payment_method_id: this.state.selected_payment_method_id,
            payment_method_name: selectedPm?.name || selected?.payment_method_name || "",
            partner_name: selected?.partner_id?.[1] || "",
            partner_phone: selected?.partner_phone || "",
            reference: selected?.name || "",
            amount_total: Number(selected?.amount_total ?? 0),
        });
        this.props.close();
    },
});
