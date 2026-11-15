/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { CompleteAdvanceOrderPopup } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/complete_advance_order_popup";
import { localAdvancesForComplete } from "@pos_local_sql_backup_advance/app/local_advance_store";

patch(CompleteAdvanceOrderPopup.prototype, {
    async _loadAdvanceOrders() {
        await super._loadAdvanceOrders(...arguments);
        const serverOrders = this.state.advance_orders || [];
        const localOrders = localAdvancesForComplete(this.props.pos).filter((local) => {
            if (local.id > 0 && serverOrders.some((order) => order.id === local.id)) {
                return false;
            }
            return true;
        });
        const byId = new Map();
        for (const order of [...localOrders, ...serverOrders]) {
            byId.set(order.id, order);
        }
        this.state.advance_orders = [...byId.values()];
        if (!serverOrders.length && localOrders.length) {
            this.notification.add(
                _t(
                    "Showing advances saved on this register. Completion stays local until Odoo is reached."
                ),
                { type: "warning" }
            );
        }
    },

    async _loadOrderDetail(orderId) {
        const selected = this.state.advance_orders.find((order) => order.id === orderId);
        if (selected?.is_local || orderId < 0) {
            this.state.detail_lines = (selected.lines || []).map((line, index) => ({
                id: index + 1,
                product_id: line.product_id
                    ? [line.product_id, line.product_name || line.product_id_name || ""]
                    : false,
                product_qty: line.product_qty ?? line.qty ?? 0,
                price_unit: line.price_unit ?? 0,
                discount: line.discount ?? 0,
                price_subtotal_incl: line.price_subtotal_incl ?? line.subtotal ?? 0,
                display_type: false,
                sequence: index + 1,
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
        if (selected?.is_local || this.state.selected_order_id < 0) {
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
                local_uuid: selected.local_uuid,
                is_local: true,
                payment_method_id: this.state.selected_payment_method_id,
                payment_method_name: selectedPm?.name || "",
                amount_tendered: this.state.amount_tendered,
                change_amount: this.remainingChangeAmount,
            });
            this.props.close();
            return;
        }
        return super.confirm(...arguments);
    },
});
