/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { rpc } from "@web/core/network/rpc";
import { AdvanceOrderFormPopup } from "./advance_order_form_popup";
import { AdvanceOrderReceipt } from "./advance_order_receipt";
import { CompleteAdvanceOrderPopup } from "./complete_advance_order_popup";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

function toNumber(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
}

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
        this.orm = useService("orm");
        this.printer = useService("printer");
    },

    /** Same breakpoints as POS `buttonClass`, but distinct hue for Advance vs default grey controls. */
    advanceOrderButtonClass() {
        if (this.props.showRemainingButtons) {
            return this.ui.isSmall
                ? "btn btn-primary btn-md py-2 text-start"
                : "btn btn-primary btn-lg py-5";
        }
        return "btn btn-primary btn-lg lh-lg";
    },

    completeAdvanceOrderButtonClass() {
        if (this.props.showRemainingButtons) {
            return this.ui.isSmall
                ? "btn btn-success btn-md py-2 text-start"
                : "btn btn-success btn-lg py-5";
        }
        return "btn btn-success btn-lg lh-lg";
    },

    _getCurrentOrder() {
        return this.currentOrder || this.pos.getOrder?.();
    },

    _getOrderPartner(order) {
        return order?.getPartner?.() || order?.partner || order?.partner_id || null;
    },

    _prepareLines(order) {
        const orderLines = order?.getOrderlines?.() || order?.lines || [];
        return orderLines
            .map((line) => {
                const product = line.getProduct?.() || line.product || line.product_id;
                const productId = product?.id || product;
                const qty = toNumber(line.getQuantity?.() ?? line.qty ?? 0);
                const priceUnit = toNumber(line.getUnitPrice?.() ?? line.price_unit ?? 0);
                if (!productId || qty <= 0) {
                    return null;
                }
                return {
                    product_id: productId,
                    product_name: product?.display_name || product?.name || "",
                    qty: qty,
                    price_unit: priceUnit,
                };
            })
            .filter(Boolean);
    },

    _buildAdvanceReceiptData({ result, partner, payload }) {
        const total = toNumber(result?.amount_total, 0);
        const advanceAmount = toNumber(result?.advance_amount, payload.advance_amount || 0);
        const amountTendered = toNumber(
            result?.amount_tendered,
            payload.amount_tendered ?? payload.advance_amount ?? 0
        );
        const changeAmount = toNumber(result?.change_amount, Math.max(amountTendered - advanceAmount, 0));
        return {
            companyName: this.pos.company?.name || "",
            posName: this.pos.config?.name || "",
            reference: result?.name || "",
            date: new Date().toLocaleString(),
            customerName: partner?.name || "",
            customerPhone: partner?.phone || partner?.mobile || "",
            paymentMethod: payload.payment_method_name || payload.payment_method,
            currencyId: this.pos.currency?.id,
            total: total,
            advanceAmount: advanceAmount,
            amountTendered: amountTendered,
            changeAmount: changeAmount,
            remainingAmount: Math.max(total - advanceAmount, 0),
            lines: (payload.lines || []).map((line) => ({
                product_id: line.product_id,
                name: line.product_name || line.full_product_name || "",
                qty: line.qty,
                subtotal: toNumber(line.qty, 0) * toNumber(line.price_unit, 0),
            })),
        };
    },

    async onClickAdvanceOrder() {
        const order = this._getCurrentOrder();
        if (!order) {
            this.notification.add(_t("No active order found."), { type: "warning" });
            return;
        }

        const partner = this._getOrderPartner(order);
        if (!partner?.id) {
            this.notification.add(_t("Please select a customer first."), { type: "warning" });
            return;
        }

        const lines = this._prepareLines(order);
        if (!lines.length) {
            this.notification.add(_t("Please add at least one product line."), { type: "warning" });
            return;
        }

        const popupPayload = await makeAwaitable(this.dialog, AdvanceOrderFormPopup, {
            pos: this.pos,
            posConfigId: this.pos.config.id,
            companyId: this.pos.company?.id,
        });
        if (!popupPayload) {
            return;
        }

        const advanceAmount = toNumber(popupPayload.advance_amount, 0);
        const amountTendered = toNumber(popupPayload.amount_tendered, advanceAmount);
        if (advanceAmount <= 0) {
            this.notification.add(_t("Advance amount must be greater than zero."), { type: "danger" });
            return;
        }
        if (amountTendered < advanceAmount) {
            this.notification.add(_t("Amount tendered cannot be less than advance amount."), { type: "danger" });
            return;
        }

        const payload = {
            partner_id: partner.id,
            pos_config_id: popupPayload.pos_config_id || this.pos.config.id,
            from_pos_config_id: popupPayload.from_pos_config_id || this.pos.config.id,
            advance_amount: advanceAmount,
            amount_tendered: amountTendered,
            payment_method_id: popupPayload.payment_method_id,
            payment_method_name: popupPayload.payment_method_name || "",
            employee_id: popupPayload.employee_id || false,
            discount_id: popupPayload.discount_id || false,
            lines: lines,
        };

        try {
            const result = await rpc("/pos/create_advance_order", payload);
            this.notification.add(_t("Advance order created: %s", result?.name || ""), { type: "success" });
            try {
                await this.printer.print(
                    AdvanceOrderReceipt,
                    {
                        receipt: this._buildAdvanceReceiptData({ result, partner, payload }),
                    },
                    this.pos.printOptions
                );
            } catch (printError) {
                const printMessage =
                    printError?.body || printError?.message || _t("Advance order created but receipt printing failed.");
                this.notification.add(printMessage, { type: "warning" });
            }
            // Reset the POS cart after successful advance creation.
            const currentOrder = this._getCurrentOrder();
            if (currentOrder) {
                this.pos.removeOrder(currentOrder);
            }
            this.pos.addNewOrder();
        } catch (error) {
            const msg = error?.data?.message || error?.message || _t("Failed to create advance order.");
            this.notification.add(msg, { type: "danger" });
        }
    },

    async onClickCompleteAdvanceOrder() {
        const popupPayload = await makeAwaitable(this.dialog, CompleteAdvanceOrderPopup, {
            posConfigId: this.pos.config.id,
            pos: this.pos,
        });
        if (!popupPayload?.advance_order_id) {
            return;
        }
        try {
            await this.orm.call(
                "pos.advance.order",
                "action_create_remaining_amount",
                [[popupPayload.advance_order_id]],
                {
                    pos_payment_method_id: popupPayload.payment_method_id,
                    pos_config_id: this.pos.config.id,
                }
            );
            this.notification.add(_t("Advance order completed successfully."), { type: "success" });
        } catch (error) {
            const msg = error?.data?.message || error?.message || _t("Failed to complete advance order.");
            this.notification.add(msg, { type: "danger" });
        }
    },
});

patch(ClosePosPopup.prototype, {
    advanceCashLineLabel() {
        return _t("Advance deposits");
    },

    advanceBankLineLabel(pm) {
        const name = pm?.name || "";
        return name ? `${_t("Advance deposits")}: ${name}` : _t("Advance deposits");
    },

    shouldShowAdvanceCashLine() {
        const dc = this.props.default_cash_details || {};
        const amt = dc.advance_payment_amount ?? 0;
        return !!(amt && this.pos.currency && !this.pos.currency.isZero(amt));
    },

    shouldShowAdvanceBankLine(pm) {
        const amt = pm?.advance_payment_amount ?? 0;
        return !!(amt && this.pos.currency && !this.pos.currency.isZero(amt));
    },
});
