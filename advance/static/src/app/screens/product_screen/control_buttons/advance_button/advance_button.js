/** @odoo-module **/

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { AdvanceReceipt } from "./advance_receipt";

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.pos = usePos();

        console.log("[ADVANCE][setup] POS instance ready", this.pos);
    },

    // ==================================================
    // Helpers
    // ==================================================

    _getCurrentPartner(order) {
        return (
            order?.partner ||
            order?.customer ||
            (order?.getPartner && order.getPartner()) ||
            null
        );
    },

    _getLineProductId(line) {
        return (
            line.product?.id ||
            line.product_id?.id ||
            line.product_id ||
            line.props?.product?.id ||
            null
        );
    },

    _getLineQty(line) {
        return (
            line.getQuantity?.() ??
            line.qty ??
            line.quantity ??
            1
        );
    },

    _getLinePrice(line) {
        return (
            line.getUnitPrice?.() ??
            line.price_unit ??
            line.price ??
            0
        );
    },

    _getOrderTotal(order) {
        if (!order) return 0;

        const lines =
            typeof order.getOrderlines === "function"
                ? order.getOrderlines()
                : order.lines || [];

        let total = 0;

        lines.forEach((line) => {
            if (line.prices) {
                total += Number(
                    line.prices.total_included_currency ??
                    line.prices.total_included ??
                    0
                );
            } else {
                total +=
                    Number(this._getLineQty(line)) *
                    Number(this._getLinePrice(line));
            }
        });

        return total;
    },

    // ==================================================
    // UI Buttons
    // ==================================================

    onClickCashAdvance() {
        this._openAdvancePopup("cash");
    },

    onClickCardAdvance() {
        this._openAdvancePopup("card");
    },

    // ==================================================
    // Popup (NO ASYNC HERE)
    // ==================================================

    _openAdvancePopup(paymentType) {
        const order = this.pos?.selectedOrder;
        if (!order) return;

        const partner = this._getCurrentPartner(order);
        if (!partner) {
            this.notification.add(
                _t("Please select a customer before taking an advance."),
                { type: "warning" }
            );
            return;
        }

        this.dialog.add(NumberPopup, {
            title: _t("Enter Advance Amount"),
            startingValue: 0,

            getPayload: (value) => {
                const amount = Number(value);
                if (!amount || amount <= 0) {
                    this.notification.add(_t("Invalid advance amount."), {
                        type: "danger",
                    });
                    return;
                }

                // ❗ لا async هنا
                this._processAdvance(order, partner, amount, paymentType);
                return amount;
            },
        });
    },

    // ==================================================
    // REAL LOGIC (ASYNC SAFE)
    // ==================================================

    async _processAdvance(order, partner, amount, paymentType) {
        try {
            const totalExpected = this._getOrderTotal(order);

            const orderLines = order.getOrderlines
                ? order.getOrderlines()
                : order.lines || [];

            const linesPayload = orderLines
                .map(line => {
                    const productId = this._getLineProductId(line);
                    if (!productId) return null;
                    return {
                        product_id: productId,
                        qty: this._getLineQty(line),
                        price_unit: this._getLinePrice(line),
                    };
                })
                .filter(Boolean);

            if (!linesPayload.length) {
                this.notification.add(
                    _t("No valid products found in order."),
                    { type: "danger" }
                );
                return;
            }

            // ================= RPC =================
            const res = await this.env.services.orm.call(
                "pos.advance.payment",
                "create_from_pos",
                [{
                    partner_id: partner.id,
                    amount_paid: amount,
                    total_expected: totalExpected,
                    payment_type: paymentType, // cash / card
                    lines: linesPayload,
                }]
            );
            order.advance_payment_id = res?.id || false;
order.advance_name = res?.name || "";
order.advance_amount = amount;
order.remaining_amount = totalExpected - amount;

            this.notification.add(
                _t("Advance created (%s)", paymentType.toUpperCase()),
                { type: "success" }
            );

            // ================= Receipt =================
            const receiptLines = orderLines.map((l, index) => ({
                key: index,
                name: l.product?.display_name || l.product?.name || _t("Unknown Product"),
                qty: this._getLineQty(l),
                price: this._getLinePrice(l),
            }));

            const receiptImage = await this.env.services.renderer.toJpeg(
                AdvanceReceipt,
                {
                    lines: receiptLines,
                    advance_amount: amount,
                    remaining_amount: totalExpected - amount,
                    formatCurrency: this.pos.env.utils.formatCurrency,
                },
                { addClass: "pos-receipt-print p-3" }
            );

            await this.pos.printReceipt({ data: receiptImage });

            // ================= Reset POS =================
            this.pos.removeOrder(order);
            const newOrder = this.pos.addNewOrder();
            this.pos.navigate("ProductScreen", {
                orderUuid: newOrder.uuid,
            });

        } catch (error) {
            console.error("[ADVANCE ERROR]", error);
            this.notification.add(
                error?.message || _t("Failed to create advance."),
                { type: "danger" }
            );
        }
    },
});
