/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { rpc } from "@web/core/network/rpc";
import { formatCurrency } from "@web/core/currency";
import { printAdvanceOrderReceipt } from "@pos_advance_order/js/advance_order_print";
import { CustomCakeFormPopup } from "./custom_cake_form_popup";
import { CakeOrdersListPopup } from "./cake_orders_list_popup";
import { CakePayLaterReceiptPopup } from "./cake_pay_later_receipt_popup";
import { CakeAdvancePaymentPopup } from "./cake_advance_payment_popup";
import { CakeCompleteAdvancePopup } from "./cake_complete_advance_popup";

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
        this.renderer = useService("renderer");
    },

    customCakeButtonClass() {
        return this.ui.isSmall
            ? "btn btn-md py-3 text-start w-100"
            : "btn btn-lg py-5 text-start w-100";
    },

    customCakeButtonStyle() {
        return "background: linear-gradient(135deg, #ff9ed2 0%, #ff69b4 45%, #e91e8c 100%); color: #fff; border: none;";
    },

    customCakeIconStyle() {
        return "font-size: 2.75rem; line-height: 1; filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));";
    },

    cakeOrdersButtonClass() {
        if (this.props.showRemainingButtons) {
            return this.ui.isSmall
                ? "btn btn-secondary btn-md py-2 text-start"
                : "btn btn-secondary btn-lg py-5 text-start";
        }
        return "btn btn-secondary btn-lg lh-lg";
    },

    get customCakeButtonLabel() {
        return _t("Custom Cake");
    },

    get cakeOrdersButtonLabel() {
        return _t("Cake Orders");
    },

    isCustomCakeEnabled() {
        const cfg = this.pos?.config;
        if (!cfg) {
            return false;
        }
        // Default to enabled when field is missing from POS data (undefined).
        return cfg.enable_custom_cake !== false;
    },

    _getCurrentOrder() {
        return this.currentOrder || this.pos.getOrder?.();
    },

    async _ensurePartner(partnerId) {
        let partner = this.pos.models["res.partner"].get(partnerId);
        if (partner) {
            return partner;
        }
        const records = await this.orm.read("res.partner", [partnerId], ["name", "phone"]);
        if (records?.length) {
            partner = this.pos.models["res.partner"].create(records[0]);
        }
        return partner;
    },

    _getCakeLinePriceUnit(product, order, result) {
        const targetTotal = result?.final_price || 0;
        const fiscalPosition = order?.fiscal_position_id || false;
        for (const candidate of [result?.price_before_tax, targetTotal]) {
            if (candidate == null) {
                continue;
            }
            const taxDetails = product.getTaxDetails({
                overridedValues: {
                    price: candidate,
                    fiscalPosition,
                },
            });
            if (Math.abs(taxDetails.total_included - targetTotal) < 0.01) {
                return candidate;
            }
        }
        return targetTotal;
    },

    async _addCakeProductToOrder({ result, partnerId }) {
        const order = this._getCurrentOrder();
        if (!order) {
            this.notification.add(_t("No active order found."), { type: "warning" });
            return false;
        }

        const partner = partnerId ? await this._ensurePartner(partnerId) : null;
        if (partner) {
            order.setPartner(partner);
        }

        const product = this.pos.models["product.product"].get(result.product_id);
        if (!product) {
            this.notification.add(_t("Cake product not found in POS."), { type: "danger" });
            return false;
        }

        await this.pos.addLineToCurrentOrder(
            {
                product_tmpl_id: product.product_tmpl_id,
                qty: 1,
                price_unit: this._getCakeLinePriceUnit(product, order, result),
            },
            {},
            false
        );

        order.setPosCakeOrderId(result.id, result.product_id);
        return true;
    },

    _buildPayLaterReceiptData(result, partner) {
        const finalPrice = result?.final_price || 0;
        return {
            companyName: this.pos.company?.name || "",
            posName: this.pos.config?.name || "",
            reference: result?.name || "",
            date: new Date().toLocaleString(),
            customerName: partner?.name || result?.partner_name || "",
            productName: result?.product_name || "",
            pieces: result?.pieces || 0,
            finalPrice,
            currencyId: this.pos.currency?.id,
            title: _t("Custom Cake Order"),
            orderNumberLabel: _t("Order Number"),
            dateLabel: _t("Date"),
            customerLabel: _t("Customer"),
            statusLabel: _t("Status"),
            statusText: _t("Waiting for Payment"),
            piecesLabel: _t("Pieces"),
            totalLabel: _t("Total"),
            finalPriceFormatted: formatCurrency(finalPrice, this.pos.currency?.id),
            footerText: _t("Please pay at the counter when ready."),
            note: result?.note || "",
            noteLabel: _t("Note"),
        };
    },

    _showPayLaterReceipt(result, partner) {
        const receipt = this._buildPayLaterReceiptData(result, partner);
        this.dialog.add(CakePayLaterReceiptPopup, {
            receipt,
        });
    },

    async _printAdvanceReceipt(receiptData) {
        return printAdvanceOrderReceipt({
            printer: this.printer,
            renderer: this.renderer,
            receiptData,
            printOptions: this.pos.printOptions,
        });
    },

    _buildCakeAdvanceReceiptData({ result, partner, advancePayload }) {
        const advance = result?.advance_order || {};
        const total = toNumber(advance.amount_total, result?.final_price || 0);
        const advanceAmount = toNumber(advance.advance_amount, advancePayload.advance_amount || 0);
        const amountTendered = toNumber(
            advance.amount_tendered,
            advancePayload.amount_tendered ?? advanceAmount
        );
        const changeDue = toNumber(
            advance.change_amount,
            Math.max(amountTendered - advanceAmount, 0)
        );
        const remainingAmount = toNumber(
            advance.amount_remaining,
            Math.max(total - advanceAmount, 0)
        );
        return {
            companyName: this.pos.company?.name || "",
            posName: this.pos.config?.name || "",
            reference: advance.name || result?.name || "",
            date: new Date().toLocaleString(),
            customerName: partner?.name || result?.partner_name || "",
            customerPhone: partner?.phone || "",
            paymentMethod: advancePayload.payment_method_name || "",
            currencyId: this.pos.currency?.id,
            total,
            pledgeAmount: toNumber(advance.pledge_amount, 0),
            advanceAmount,
            amountTendered,
            changeDue,
            remainingAmount,
            isRefund: false,
            lines: [
                {
                    product_id: result?.product_id,
                    name: result?.product_name || "",
                    qty: 1,
                    discount: 0,
                    subtotal: total,
                },
            ],
        };
    },

    _buildCakeCompletionReceiptData({ result, popupPayload }) {
        const total = toNumber(result?.amount_total, 0);
        const advanceAmount = toNumber(result?.advance_amount, 0);
        const remainingPaid = toNumber(result?.remaining_paid, Math.max(total - advanceAmount, 0));
        const amountTendered = toNumber(
            result?.remaining_amount_tendered,
            popupPayload.amount_tendered ?? remainingPaid
        );
        const changeDue = toNumber(
            result?.remaining_change_amount,
            popupPayload.change_amount ?? Math.max(amountTendered - remainingPaid, 0)
        );
        return {
            companyName: this.pos.company?.name || "",
            posName: this.pos.config?.name || "",
            reference: result?.cake_order_name || result?.name || "",
            posOrderReference: result?.pos_order_name || "",
            date: new Date().toLocaleString(),
            customerName: result?.partner_name || "",
            customerPhone: result?.partner_phone || "",
            advancePaymentMethod: result?.advance_payment_method_name || "",
            paymentMethod: result?.payment_method_name || popupPayload.payment_method_name || "",
            currencyId: this.pos.currency?.id,
            total,
            advanceAmount,
            remainingPaid,
            amountTendered,
            changeDue,
            pledgeAmount: toNumber(result?.pledge_amount, 0),
            remainingAmount: 0,
            isRefund: false,
            isCompletion: true,
            lines: (result?.lines || []).map((line) => ({
                name: line.name || "",
                qty: toNumber(line.qty, 0),
                discount: toNumber(line.discount, 0),
                subtotal: toNumber(line.subtotal, 0),
                isPledgeLine: !!line.is_pledge_line,
            })),
            pledgeLines: (result?.pledge_lines || []).map((line) => ({
                name: line.name || "",
                qty: toNumber(line.qty, 0),
                subtotal: toNumber(line.subtotal, 0),
            })),
        };
    },

    async _handleCakePayAdvance(popupResult) {
        const advancePayload = await makeAwaitable(this.dialog, CakeAdvancePaymentPopup, {
            pos: this.pos,
            cakeTotal: popupResult.prices?.final_price || 0,
            partnerName: popupResult.partner?.name || "",
        });
        if (!advancePayload) {
            return;
        }

        const payload = {
            ...popupResult.payload,
            advance_amount: advancePayload.advance_amount,
            amount_tendered: advancePayload.amount_tendered,
            payment_method_id: advancePayload.payment_method_id,
            from_pos_config_id: this.pos.config.id,
            deposit_pos_session_id: this.pos.session?.id,
        };

        const result = await rpc("/pos/custom_cake/create_order_with_advance", payload);
        const moLabel = result?.production_name ? _t("MO: %s", result.production_name) : "";
        this.notification.add(
            _t("Cake advance saved: %s %s", result?.name || "", moLabel).trim(),
            { type: "success" }
        );
        try {
            const printResult = await this._printAdvanceReceipt(
                this._buildCakeAdvanceReceiptData({
                    result,
                    partner: popupResult.partner,
                    advancePayload,
                })
            );
            if (!printResult?.printed) {
                this.notification.add(_t("Cake advance created but receipt printing failed."), {
                    type: "warning",
                });
            }
        } catch (printError) {
            const printMessage =
                printError?.message === "POPUP_BLOCKED"
                    ? _t("Please allow pop-ups to print the advance receipt.")
                    : printError?.body ||
                      printError?.message ||
                      _t("Cake advance created but receipt printing failed.");
            this.notification.add(printMessage, { type: "warning" });
        }
    },

    async _handleCakeCompleteAdvance(order) {
        const popupPayload = await makeAwaitable(this.dialog, CakeCompleteAdvancePopup, {
            pos: this.pos,
            order,
        });
        if (!popupPayload?.order_id) {
            return;
        }
        const result = await rpc("/pos/custom_cake/complete_advance", {
            order_id: popupPayload.order_id,
            pos_config_id: this.pos.config.id,
            payment_method_id: popupPayload.payment_method_id,
            amount_tendered: popupPayload.amount_tendered,
        });
        this.notification.add(_t("Cake advance completed successfully."), { type: "success" });
        try {
            const receiptPayload =
                result && typeof result === "object" && (result.name || result.cake_order_name)
                    ? result
                    : null;
            if (receiptPayload) {
                const printResult = await this._printAdvanceReceipt(
                    this._buildCakeCompletionReceiptData({
                        result: receiptPayload,
                        popupPayload,
                    })
                );
                if (!printResult?.printed) {
                    this.notification.add(
                        _t("Cake advance completed but receipt printing failed."),
                        { type: "warning" }
                    );
                }
            }
        } catch (printError) {
            const printMessage =
                printError?.message === "POPUP_BLOCKED"
                    ? _t("Please allow pop-ups to print the completion receipt.")
                    : printError?.body ||
                      printError?.message ||
                      _t("Cake advance completed but receipt printing failed.");
            this.notification.add(printMessage, { type: "warning" });
        }
    },

    async onClickCustomCake() {
        if (!this.isCustomCakeEnabled()) {
            this.notification.add(_t("Custom Cake is not enabled on this POS."), { type: "warning" });
            return;
        }

        const popupResult = await makeAwaitable(this.dialog, CustomCakeFormPopup, {
            pos: this.pos,
        });
        if (!popupResult) {
            return;
        }

        try {
            if (popupResult.action === "pay_advance") {
                await this._handleCakePayAdvance(popupResult);
                return;
            }

            const result = await rpc("/pos/custom_cake/create_order", popupResult.payload);

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
                const moLabel = result?.production_name
                    ? _t("MO: %s", result.production_name)
                    : "";
                this.notification.add(
                    _t("Custom cake added: %s %s", result?.name || "", moLabel).trim(),
                    { type: "success" }
                );
            }
        } catch (error) {
            const msg =
                error?.data?.message || error?.message || _t("Failed to create custom cake order.");
            this.notification.add(msg, { type: "danger" });
        }
    },

    async onClickCakeOrders() {
        if (!this.isCustomCakeEnabled()) {
            this.notification.add(_t("Custom Cake is not enabled on this POS."), { type: "warning" });
            return;
        }

        const popupResult = await makeAwaitable(this.dialog, CakeOrdersListPopup, {
            pos: this.pos,
        });
        if (!popupResult?.order) {
            return;
        }

        try {
            if (popupResult.order.state === "advance_paid") {
                await this._handleCakeCompleteAdvance(popupResult.order);
                return;
            }

            const result = await rpc("/pos/custom_cake/get_order", {
                order_id: popupResult.order.id,
            });

            const added = await this._addCakeProductToOrder({
                result,
                partnerId: result.partner_id,
            });
            if (added) {
                this.notification.add(
                    _t("Cake order loaded: %s", result?.name || ""),
                    { type: "success" }
                );
            }
        } catch (error) {
            const msg =
                error?.data?.message || error?.message || _t("Failed to load cake order.");
            this.notification.add(msg, { type: "danger" });
        }
    },
});
