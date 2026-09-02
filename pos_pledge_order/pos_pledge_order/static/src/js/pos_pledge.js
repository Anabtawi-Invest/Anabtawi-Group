/** @odoo-module */

const PLEDGE_ORDER_BUILD_TAG = "PLEDGE_ORDER_BUILD_2026_08_11_MULTI_RETURN";
console.log("[PLEDGE] Module loading started...", PLEDGE_ORDER_BUILD_TAG);

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PledgeListPopup } from "@pos_pledge_order/js/pledge_list_popup";
import { EmployeeSelectionPopup } from "@pos_pledge_order/js/employee_selection_popup";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import {
    computeMappedPledgeDetails,
    getLineProduct,
    getPledgeProductForMenuProduct,
    lineHasPledgeMapping,
    menuProductHasPledgeMapping,
    orderHasMappedPledgeProducts,
    resolvePledgeUnitAmount,
} from "@pos_pledge_order/js/pledge_mapping_utils";

console.log("[PLEDGE] All imports successful");

// =============================================================================
// Helper function to print HTML receipts
// =============================================================================
function printHtmlReceipt(html, title = 'Receipt') {
    const printWindow = window.open('', '_blank', 'width=300,height=600');
    printWindow.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <title>${title}</title>
            <style>
                body { font-family: monospace; width: 300px; margin: 20px auto; }
                .pos-receipt { padding: 10px; }
                .text-center { text-align: center; }
                .text-end { text-align: right; }
                .mb-1, .mb-2, .mb-3, .mt-3, .mt-4 { margin-bottom: 10px; }
                .d-flex { display: flex; }
                .justify-content-between { justify-content: space-between; }
                .flex-grow-1 { flex-grow: 1; }
                .product-detail { font-size: 0.9em; color: #666; }
                .table-borderless { width: 100%; border-top: 2px solid #000; padding-top: 10px; }
                .badge { display: inline-block; padding: 2px 6px; font-size: 0.7em; border-radius: 3px; margin-left: 5px; }
                .bg-warning { background-color: #ffc107; color: #000; }
                .bg-info { background-color: #17a2b8; color: #fff; }
                .bg-primary { background-color: #007bff; color: #fff; }
                .alert-warning { background-color: #fff3cd; border: 1px solid #856404; color: #856404; padding: 10px; }
                @media print {
                    body { margin: 0; width: 80mm; }
                }
            </style>
        </head>
        <body onload="window.print(); setTimeout(() => window.close(), 100);">
            ${html}
        </body>
        </html>
    `);
    printWindow.document.close();
}

function orderHasPledgeProducts(order, pos) {
    const context = pos || (order?.models ? { models: order.models } : null);
    if (!context) {
        return false;
    }
    return orderHasMappedPledgeProducts(order, context);
}

function getOrderPricelistName(order, pos) {
    const orderPricelist =
        (typeof order?.get_pricelist === "function" && order.get_pricelist()) ||
        (typeof order?.getPricelist === "function" && order.getPricelist()) ||
        order?.pricelist ||
        order?.pricelist_id ||
        pos?.config?.pricelist_id ||
        pos?.default_pricelist;
    return (
        orderPricelist?.name ||
        (Array.isArray(orderPricelist) ? orderPricelist[1] : null) ||
        ""
    );
}

// =============================================================================
// Guard against occasional race where product template is not yet loaded
// (seen on pos_sale down-payment flow during validate/deposit).
// =============================================================================
patch(PosStore.prototype, {
    addLineToCurrentOrder(vals, opts = {}, configure = true) {
        const safeVals = vals ? { ...vals } : {};
        const productModel = this.data?.models?.["product.product"];
        const templateModel = this.data?.models?.["product.template"];

        const normalizeId = (value) => {
            if (!value) return null;
            if (typeof value === "number") return value;
            if (Array.isArray(value)) return value[0] || null;
            if (typeof value === "object" && value.id) return value.id;
            return null;
        };

        const resolveTemplateRecord = (value) => {
            if (!value) return null;
            if (typeof value === "object" && !Array.isArray(value) && ("sale_line_warn_msg" in value || "name" in value)) {
                return value;
            }
            const templateId = normalizeId(value);
            return templateId ? templateModel?.get(templateId) || null : null;
        };

        const resolveProductRecord = (value) => {
            if (!value) return null;
            if (typeof value === "object" && !Array.isArray(value) && value.id && value.product_tmpl_id) {
                return value;
            }
            const productId = normalizeId(value);
            return productId ? productModel?.get(productId) || null : null;
        };

        if (!safeVals.product_tmpl_id && safeVals.product_id?.product_tmpl_id) {
            safeVals.product_tmpl_id = safeVals.product_id.product_tmpl_id;
        }

        if (!safeVals.product_tmpl_id && typeof safeVals.product_id === "number") {
            const product = productModel?.get(safeVals.product_id);
            if (product?.product_tmpl_id) {
                safeVals.product_tmpl_id = product.product_tmpl_id;
            }
        }

        if (!safeVals.product_tmpl_id && safeVals.product_id?.id) {
            const product = productModel?.get(safeVals.product_id.id);
            if (product?.product_tmpl_id) {
                safeVals.product_tmpl_id = product.product_tmpl_id;
            }
        }

        const productRecord = resolveProductRecord(safeVals.product_id);
        if (productRecord) {
            safeVals.product_id = productRecord;
        }
        if (!safeVals.product_tmpl_id && productRecord?.product_tmpl_id) {
            safeVals.product_tmpl_id = productRecord.product_tmpl_id;
        }

        const templateRecord = resolveTemplateRecord(safeVals.product_tmpl_id);
        if (templateRecord) {
            safeVals.product_tmpl_id = templateRecord;
        }

        if (!safeVals.product_tmpl_id) {
            console.warn("[PLEDGE] addLineToCurrentOrder: unresolved product template.", safeVals);
            this.notification?.add(
                _t("Product template is not ready yet. Please retry."),
                { type: "warning" }
            );
            return null;
        }

        try {
            return super.addLineToCurrentOrder(safeVals, opts, configure);
        } catch (error) {
            if (String(error?.message || "").includes("sale_line_warn_msg")) {
                console.error("[PLEDGE] Guarded addLineToCurrentOrder crash:", error, safeVals);
                this.notification?.add(
                    _t("Product data is still initializing. Please try again."),
                    { type: "warning" }
                );
                return null;
            }
            throw error;
        }
    },
});

// =============================================================================
// 1. Pledge processing is now automatic (no popup needed)
// =============================================================================
// The pledge flow is handled automatically when validating orders with pledge items

// =============================================================================
// 2. Patch ControlButtons to add Return Pledge button
// =============================================================================

patch(ControlButtons.prototype, {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.pos = usePos();
    },

    /**
     * Handle Return Pledge button click
     */
    get selectEmployeeLabel() {
        return _t("Select Employee");
    },

    get returnPledgeLabel() {
        return _t("Return Pledge");
    },

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

            const result = await this.env.services.orm.call(
                "pos.advance.order.pledge",
                "action_return_pledges",
                [selection.pledge_ids],
                {
                    pos_payment_method_id: selection.payment_method_id,
                    pos_session_id: this.pos.session?.id || false,
                }
            );

            const refundCount = result?.count || (result?.refund_order_name ? 1 : 0);
            const pledgeCount = selection.pledge_ids.length;
            if (refundCount > 1) {
                this.notification.add(
                    _t(
                        "%s pledge(s) returned in %s refund order(s).",
                        pledgeCount,
                        refundCount
                    ),
                    { type: "success" }
                );
            } else {
                this.notification.add(
                    _t("%s pledge(s) returned successfully.", pledgeCount),
                    { type: "success" }
                );
            }
        } catch (error) {
            console.error("[PLEDGE] Error returning pledge:", error);
            this.notification.add(
                error.message || error.data?.message || _t("Failed to return pledge"),
                { type: "danger" }
            );
        }
    },

    /**
     * Handle Select Employee button click
     */
    async onClickSelectEmployee() {
        console.log("[PLEDGE] Select Employee button clicked!");
        try {
            const order = this.pos.getOrder();
            if (!order) {
                this.notification.add(
                    _t("No order selected"),
                    { type: "warning" }
                );
                return;
            }

            // Show employee selection popup
            const selectedEmployee = await new Promise((resolve) => {
                this.dialog.add(EmployeeSelectionPopup, {
                    getPayload: (payload) => {
                        console.log("[PLEDGE] User selected employee:", payload);
                        resolve(payload);
                    },
                });
            });

            if (!selectedEmployee) {
                console.log("[PLEDGE] No employee selected, cancelling");
                return;
            }

            console.log("[PLEDGE] Selected employee:", selectedEmployee);

            // Set employee on order
            order.employee_id = selectedEmployee.id;
            order.employee_name = selectedEmployee.name;

            console.log("[PLEDGE] ✓ Employee set on order:", selectedEmployee.name);

            this.notification.add(
                _t("Employee selected: %s", selectedEmployee.name),
                { type: "success" }
            );

        } catch (error) {
            console.error("[PLEDGE] Error selecting employee:", error);
            this.notification.add(
                error.message || _t("Failed to select employee"),
                { type: "danger" }
            );
        }
    },
});

console.log("[PLEDGE] ControlButtons patch applied");

// =============================================================================
// 2.5. Patch PosOrder to support employee_id and employee_name
// =============================================================================
patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        // Do not overwrite employee_id: pos_hr stores the PIN cashier as a record.
        this.employee_name = vals?.employee_name || this.employee_id?.name || null;
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        // POS many2one records serialize as objects; Postgres needs an integer ID.
        const employee = this.employee_id;
        if (employee) {
            data.employee_id = employee.id ?? employee;
        }
        const lines = this.getOrderlines ? this.getOrderlines() : this.lines || [];
        console.warn(
            "[PLEDGE][TRACE][FRONT] serializeForORM build=%s order=%s employee_id=%s lines=%s payload_lines=%s",
            PLEDGE_ORDER_BUILD_TAG,
            this.name || this.uid || "n/a",
            data.employee_id || "none",
            lines.length,
            (data.lines || []).length
        );
        lines.forEach((line, idx) => {
            const product = getLineProduct(line);
            console.warn(
                "[PLEDGE][TRACE][FRONT] line#%s product=%s id=%s qty=%s unit=%s has_pledge_mapping=%s",
                idx + 1,
                product?.display_name || product?.name || "unknown",
                product?.id || "n/a",
                line.get_quantity ? line.get_quantity() : (line.qty || 0),
                line.get_unit_price ? line.get_unit_price() : (line.price_unit || 0),
                menuProductHasPledgeMapping({ models: this.models }, product)
            );
        });
        return data;
    },
});

console.log("[PLEDGE] PosOrder patch applied");

// =============================================================================
// 2.6. Require customer when order contains pledge products
// =============================================================================
patch(PosOrder.prototype, {
    get isCustomerRequired() {
        if (!this.partner_id && orderHasPledgeProducts(this)) {
            return true;
        }
        if (this.partner_id) {
            return false;
        }
        const splitPayment = this.payment_ids.some(
            (payment) => payment.payment_method_id.split_transactions
        );
        const invalidPartnerPreset =
            (this.preset_id?.needsName && !this.floating_order_name) ||
            this.preset_id?.needsPartner;
        return invalidPartnerPreset || this.isToInvoice() || Boolean(splitPayment);
    },
});

patch(OrderPaymentValidation.prototype, {
    async isOrderValid(isForceValidate) {
        if (orderHasPledgeProducts(this.order) && !this.order.getPartner()) {
            const confirmed = await ask(this.pos.dialog, {
                title: _t("Customer Required"),
                body: _t(
                    "This order has a pledge. Please choose a customer before proceeding."
                ),
            });
            if (confirmed) {
                this.pos.selectPartner();
            }
            return false;
        }
        return super.isOrderValid(isForceValidate);
    },
});

console.log("[PLEDGE] Customer required for pledge orders patch applied");

patch(PosStore.prototype, {
    async pay() {
        const currentOrder = this.getOrder();
        if (orderHasPledgeProducts(currentOrder) && !currentOrder.getPartner()) {
            await new Promise((resolve) => {
                this.dialog.add(
                    AlertDialog,
                    {
                        title: _t("Customer Required"),
                        body: _t(
                            "This order has a pledge. Please choose a customer before proceeding."
                        ),
                    },
                    { onClose: resolve }
                );
            });
            await this.selectPartner(currentOrder);
            if (!currentOrder.getPartner()) {
                return;
            }
        }
        return super.pay(...arguments);
    },
});

// =============================================================================
// 3. Patch PaymentScreen to automatically handle pledge on validation
// =============================================================================
patch(PaymentScreen.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.pos = usePos();
        console.log("[PLEDGE] PaymentScreen setup complete");
    },
    
    async validateOrder(isForceValidate) {
        const order = this.pos.selectedOrder;
        
        console.log("[PLEDGE] validateOrder called");
        
        // Check if order has employee service products
        const lines = order.getOrderlines ? order.getOrderlines() : order.lines || [];
        
        const hasEmployeeService = lines.some(line => {
            const product = line.getProduct ? line.getProduct() : (line.product || line.product_id);
            return product?.is_employee_service;
        });
        
        const hasDeliveryProduct = lines.some(line => {
            const product = line.getProduct ? line.getProduct() : (line.product || line.product_id);
            return product?.is_delivery_product;
        });
        
        // Check if both employee service and delivery product exist together
        if (hasEmployeeService && hasDeliveryProduct) {
            console.log("[PLEDGE] ⚠️ Order has both employee service and delivery product - not allowed");
            this.notification.add(
                _t("Error: Employee service and delivery service cannot be in the same order. Please choose one of them."),
                { type: "danger" }
            );
            return; // Prevent validation
        }
        
        if (hasEmployeeService && !order.employee_id) {
            console.log("[PLEDGE] ⚠️ Order has employee service but no employee selected");
            this.notification.add(
                _t("Please select an employee before validating this order. The order contains employee service products."),
                { type: "warning" }
            );
            return; // Prevent validation
        }

        if (orderHasPledgeProducts(order) && !order.getPartner?.()) {
            console.log("[PLEDGE] ⚠️ Order has pledge products but no customer selected");
            this.notification.add(
                _t("This order has a pledge. Please choose a customer before proceeding."),
                { type: "warning" }
            );
            return; // Prevent validation
        }
        
        // Check if order has pledge items
        const hasPledgeItems = this._checkPledgeItems(order);
        console.log("[PLEDGE] Has pledge items:", hasPledgeItems);
        
        if (hasPledgeItems) {
            console.log("[PLEDGE] ✅ Order has pledge items - processing pledge scenario automatically");
            
            // Detect and prepare pledge data
            const pledgeData = this._preparePledgeData(order);
            
            if (pledgeData) {
                order.pledgeData = pledgeData;
                order.hasPledge = true;
                console.log("[PLEDGE] ✅ Pledge data prepared:", pledgeData);
                console.log("[PLEDGE] Case Type:", pledgeData.case_type);
                console.log("[PLEDGE] Pledge Amount:", pledgeData.pledge_amount);
                console.log("[PLEDGE] Employee Amount:", pledgeData.employee_amount);
                console.log("[PLEDGE] Delivery Amount:", pledgeData.delivery_amount);
            } else {
                console.log("[PLEDGE] ⚠️ Could not prepare pledge data");
            }
        }
        
        // Continue with normal validation
        console.log("[PLEDGE] Proceeding with normal order validation");
        
        try {
            const result = await super.validateOrder(isForceValidate);
            console.log("[PLEDGE] ✅ Validation completed successfully");
            
            // Pledge creation is handled in backend (pos.order write flow) to avoid duplicate records.
            if (order.hasPledge && order.pledgeData) {
                console.log("[PLEDGE] Backend pledge flow will create related records (frontend creation skipped).");
            }
            
            return result;
        } catch (error) {
            console.error("[PLEDGE] ✗ Error in validateOrder:", error);
            throw error;
        }
    },
    
    async _finalizeValidation() {
        console.log("[PLEDGE] _finalizeValidation called");
        const result = await super._finalizeValidation(...arguments);
        console.log("[PLEDGE] super._finalizeValidation result:", result);
        
        const order = this.pos.selectedOrder;
        console.log("[PLEDGE] Current order:", order);
        console.log("[PLEDGE] order.hasPledge:", order.hasPledge);
        console.log("[PLEDGE] order.pledgeData:", order.pledgeData);
        console.log("[PLEDGE] result:", result);
        
        // Keep finalize hook passive; backend handles pledge line creation to prevent duplicates.
        if (order?.hasPledge) {
            console.log("[PLEDGE] _finalizeValidation: backend pledge flow active, skipping frontend create.");
        }
        
        return result;
    },

    /**
     * Override printReceipt to filter delivery products if employee service exists
     */
    async printReceipt() {
        const order = this.currentOrder;
        
        if (!order) {
            return await super.printReceipt(...arguments);
        }
        
        console.log("[PLEDGE] printReceipt called - checking for employee service");
        
        const lines = order.lines || [];
        const hasEmployeeService = lines.some(line => {
            const product = line.get_product();
            return product?.is_employee_service === true;
        });
        
        console.log("[PLEDGE] Has employee service:", hasEmployeeService);
        
        if (hasEmployeeService) {
            // Temporarily hide delivery products from orderlines
            const hiddenLines = [];
            
            lines.forEach(line => {
                const product = line.get_product();
                if (product?.is_delivery_product) {
                    console.log("[PLEDGE] Temporarily hiding delivery product for print:", product.display_name);
                    line._tempHidden = true;
                    hiddenLines.push(line);
                }
            });
            
            // Print with filtered lines
            await super.printReceipt(...arguments);
            
            // Restore hidden lines
            hiddenLines.forEach(line => {
                delete line._tempHidden;
            });
            
            console.log("[PLEDGE] Restored hidden lines");
        } else {
            // No employee service - print normally
            await super.printReceipt(...arguments);
        }
    },

    /**
     * Override to add dual receipt printing after validation
     */
    async _showNextScreen() {
        // No automatic printing - let user choose which receipt to print
        console.log("[PLEDGE] Showing receipt screen - user can choose receipt type");
        return await super._showNextScreen(...arguments);
    },

    /**
     * Print both internal and customer receipts
     */
    async _printDualReceipts(order) {
        try {
            // Prepare receipt data with pledge information
            const receiptData = this._prepareReceiptData(order);
            
            console.log("[PLEDGE] Receipt data prepared");
            console.log("[PLEDGE] All orderlines:", receiptData.orderlines?.length || 0);
            console.log("[PLEDGE] Customer orderlines:", receiptData.customerOrderlines?.length || 0);
            console.log("[PLEDGE] Customer total:", receiptData.customer_total);
            
            // Print both receipts using the standard POS receipt printer
            console.log("[PLEDGE] Printing internal receipt (all items)...");
            const internalHtml = this._buildInternalReceiptHtml(receiptData);
            printHtmlReceipt(internalHtml, 'Internal Receipt');
            
            // Small delay between prints
            await new Promise(resolve => setTimeout(resolve, 500));
            
            console.log("[PLEDGE] Printing customer receipt (filtered)...");
            const customerHtml = this._buildCustomerReceiptHtml(receiptData);
            printHtmlReceipt(customerHtml, 'Customer Receipt');
            
            console.log("[PLEDGE] ✅ Both receipts printed successfully");
            
            this.notification.add(
                _t("Dual receipts printed: Internal + Customer"),
                { type: "success" }
            );
        } catch (error) {
            console.error("[PLEDGE] Error printing dual receipts:", error);
            this.notification.add(
                _t("Warning: Failed to print one or more pledge receipts"),
                { type: "warning" }
            );
        }
    },

    /**
     * Prepare receipt data with pledge information
     * NOTE: This is used for custom customer receipt only
     * The standard "Print Full Receipt" uses default Odoo receipt + QWeb inheritance
     */
    _prepareReceiptData(order) {
        const receiptData = order.export_for_printing();
        const lines = order.getOrderlines ? order.getOrderlines() : order.lines || [];
        receiptData.pricelist_name = getOrderPricelistName(order, this.pos);
        const pledgeInfo = computeMappedPledgeDetails(order, this.pos);

        receiptData.orderlines.forEach((receiptLine, index) => {
            const orderline = lines[index];
            if (orderline) {
                const menuProduct = getLineProduct(orderline);
                const pledgeProduct = getPledgeProductForMenuProduct(this.pos, menuProduct);
                receiptLine.has_pledge = Boolean(pledgeProduct);
                receiptLine.pledge_amount = pledgeProduct
                    ? resolvePledgeUnitAmount(pledgeProduct)
                    : 0;
                receiptLine.is_employee_service = menuProduct?.is_employee_service || false;
            }
        });

        receiptData.pledgeDetails = pledgeInfo.pledgeDetails;
        receiptData.totalPledgeAmount = pledgeInfo.totalPledgeAmount;
        receiptData.hasPledgeProducts = pledgeInfo.hasPledge;

        // Create customer orderlines - include ALL products with product prices
        // Virtual pledge lines are automatically excluded (not in order.lines)
        const customerLines = [];
        let customerTotal = 0;
        
        lines.forEach(line => {
            const product = line.product || line.product_id;
            // Include ALL products - pledge products show with their product price only
            const quantity = line.get_quantity ? line.get_quantity() : line.qty;
            const unitPrice = line.get_unit_price ? line.get_unit_price() : line.price_unit;
            const priceWithTax = line.get_price_with_tax ? line.get_price_with_tax() : line.price_subtotal_incl;
            
            customerLines.push({
                product_name: product.display_name || product.name,
                quantity: quantity.toString(),
                price: this.env.utils.formatCurrency(unitPrice, false),
                price_display: this.env.utils.formatCurrency(priceWithTax, false),
            });
            
            customerTotal += priceWithTax;
        });

        receiptData.customerOrderlines = customerLines;
        receiptData.customer_total = this.env.utils.formatCurrency(customerTotal, false);
        receiptData.hasPledge = order.hasPledge || false;

        return receiptData;
    },

    /**
     * Build internal receipt HTML (with all items including pledge/employee/delivery)
     */
    _buildInternalReceiptHtml(receiptData) {
        let html = `
            <div class="pos-receipt internal-receipt" style="background-color: #fff3cd; border: 3px dashed #856404; padding: 20px;">
                <div class="pos-receipt-header">
                    <h2 class="text-center mb-3" style="color: #856404; font-weight: bold; border-bottom: 2px solid #856404; padding-bottom: 10px;">
                        <strong>⚠️ INTERNAL RECEIPT ⚠️</strong>
                    </h2>
                    <div class="text-center mb-2">
                        <div class="mb-1">${receiptData.company.name || ''}</div>
                        ${receiptData.company.street ? `<div>${receiptData.company.street}</div>` : ''}
                        ${receiptData.company.phone ? `<div>Tel: ${receiptData.company.phone}</div>` : ''}
                    </div>
                    <div class="cashier mb-2">
                        <div>Cashier: ${receiptData.cashier || ''}</div>
                        <div>Order: ${receiptData.name || ''}</div>
                        <div>Date: ${receiptData.date || ''}</div>
                    </div>
                    ${receiptData.partner ? `
                        <div class="partner-info mb-2">
                            <div><strong>Customer: ${receiptData.partner.name}</strong></div>
                            ${receiptData.partner.phone ? `<div>Phone: ${receiptData.partner.phone}</div>` : ''}
                        </div>
                    ` : ''}
                </div>
                <div class="pos-receipt-body">
                    <div class="orderlines">
        `;

        // Add ALL orderlines with badges
        receiptData.orderlines.forEach(line => {
            const badges = [];
            if (line.has_pledge) badges.push('<span class="badge bg-warning text-dark ms-1">PLEDGE</span>');
            if (line.is_employee_service) badges.push('<span class="badge bg-info text-dark ms-1">EMPLOYEE</span>');
            if (line.is_virtual_pledge) badges.push('<span class="badge bg-success text-white ms-1">VIRTUAL PLEDGE</span>');
            
            html += `
                        <div class="orderline" style="${line.is_pledge_related ? 'background-color: #fff9e6; border-left: 4px solid #ffc107; padding-left: 8px;' : ''}">
                            <div class="d-flex justify-content-between">
                                <div class="flex-grow-1">
                                    <div class="product-name">${line.product_name} ${badges.join(' ')}</div>
                                    <div class="product-detail text-muted">${line.quantity} x ${line.price}</div>
                                </div>
                                <div class="price text-end">${line.price_display}</div>
                            </div>
                        </div>
            `;
        });

        html += `
                    </div>
                    <div class="pos-receipt-amount mt-3" style="border-top: 2px solid #000; padding-top: 10px;">
                        <table class="table-borderless w-100">
                            <tr>
                                <td class="text-end"><strong>TOTAL:</strong></td>
                                <td class="text-end price"><strong>${receiptData.total_with_tax}</strong></td>
                            </tr>
                        </table>
                    </div>
                </div>
                <div class="pos-receipt-footer text-center mt-4">
                    <div class="alert alert-warning" style="background-color: #fff3cd; border: 1px solid #856404; color: #856404; padding: 10px; border-radius: 5px;">
                        <strong>FOR INTERNAL USE ONLY</strong><br/>
                        This receipt contains pledge/service details
                    </div>
                </div>
            </div>
        `;

        return html;
    },

    /**
     * Build customer receipt HTML (filtered - no pledge/employee/delivery)
     */
    _buildCustomerReceiptHtml(receiptData) {
        let html = `
            <div class="pos-receipt customer-receipt">
                <div class="pos-receipt-header">
                    <h2 class="text-center mb-3">RECEIPT</h2>
                    <div class="text-center mb-2">
                        <div class="mb-1">${receiptData.company.name || ''}</div>
                        ${receiptData.company.street ? `<div>${receiptData.company.street}</div>` : ''}
                        ${receiptData.company.phone ? `<div>Tel: ${receiptData.company.phone}</div>` : ''}
                    </div>
                    <div class="cashier mb-2">
                        <div>Cashier: ${receiptData.cashier || ''}</div>
                        <div>Order: ${receiptData.name || ''}</div>
                        <div>Date: ${receiptData.date || ''}</div>
                        ${receiptData.pricelist_name ? `<div>Pricelist: ${receiptData.pricelist_name}</div>` : ''}
                    </div>
                    ${receiptData.partner ? `
                        <div class="partner-info mb-2">
                            <div><strong>Customer: ${receiptData.partner.name}</strong></div>
                            ${receiptData.partner.phone ? `<div>Phone: ${receiptData.partner.phone}</div>` : ''}
                        </div>
                    ` : ''}
                </div>
                <div class="pos-receipt-body">
                    <div class="orderlines">
        `;

        // Add customer orderlines only
        receiptData.customerOrderlines.forEach(line => {
            html += `
                        <div class="orderline">
                            <div class="d-flex justify-content-between">
                                <div class="flex-grow-1">
                                    <div class="product-name">${line.product_name}</div>
                                    <div class="product-detail text-muted">${line.quantity} x ${line.price}</div>
                                </div>
                                <div class="price text-end">${line.price_display}</div>
                            </div>
                        </div>
            `;
        });

        html += `
                    </div>
                    <div class="pos-receipt-amount mt-3">
                        <table class="table-borderless w-100">
                            <tr>
                                <td class="text-end"><strong>TOTAL:</strong></td>
                                <td class="text-end price"><strong>${receiptData.customer_total}</strong></td>
                            </tr>
                        </table>
                    </div>
                </div>
                <div class="pos-receipt-footer text-center mt-4">
                    <div>Thank you for your business!</div>
                </div>
            </div>
        `;

        return html;
    },

    _checkPledgeItems(order) {
        if (!order) return false;

        const lines = order.getOrderlines ? order.getOrderlines() : order.lines || [];
        const posContext = this.pos || (order.models ? { models: order.models } : null);
        return lines.some((line) => {
            const product = getLineProduct(line);
            return (
                (posContext && lineHasPledgeMapping(posContext, line)) ||
                product?.is_employee_service
            );
        });
    },

    _preparePledgeData(order) {
        const lines = order.getOrderlines ? order.getOrderlines() : order.lines || [];
        const posContext = this.pos || (order.models ? { models: order.models } : null);
        const pledgeInfo = posContext ? computeMappedPledgeDetails(order, posContext) : {
            totalPledgeAmount: 0,
            pledgeDetails: [],
            pledgeProductIds: [],
            hasPledge: false,
        };

        const hasEmployee = lines.some((l) => getLineProduct(l)?.is_employee_service);
        const hasPledge = pledgeInfo.hasPledge;
        const hasDelivery = lines.some((l) => getLineProduct(l)?.is_delivery_product);
        
        // Determine case type based on what's present
        let caseType = null;
        if (hasEmployee && !hasPledge && !hasDelivery) {
            caseType = 'case1'; // Employee Only
        } else if (hasPledge && !hasDelivery && !hasEmployee) {
            caseType = 'case2'; // Pledge Only
        } else if (hasPledge && hasDelivery && !hasEmployee) {
            caseType = 'case3'; // Pledge + Delivery
        } else if (hasPledge && hasEmployee && hasDelivery) {
            caseType = 'case4'; // All Three: Pledge + Employee + Delivery
        } else if (hasPledge && hasEmployee && !hasDelivery) {
            caseType = 'case5'; // Pledge + Employee (no delivery)
        } else if (hasEmployee && hasDelivery && !hasPledge) {
            caseType = 'case6'; // Employee + Delivery (no pledge)
        } else {
            // Default: accept any combination
            caseType = 'mixed';
            console.log("[PLEDGE] Mixed pledge scenario detected:", {hasEmployee, hasPledge, hasDelivery});
        }
        
        console.log("[PLEDGE] Detected case:", caseType);
        
        let pledgeAmount = pledgeInfo.totalPledgeAmount;
        let employeeAmount = 0;
        let deliveryAmount = 0;

        lines.forEach((line) => {
            const product = getLineProduct(line);
            let price = 0;
            if (typeof line.get_price_with_tax === "function") {
                price = line.get_price_with_tax();
            } else if (typeof line.getPriceWithTax === "function") {
                price = line.getPriceWithTax();
            } else if (line.price_subtotal_incl !== undefined) {
                price = line.price_subtotal_incl;
            } else {
                const qty = line.quantity || line.qty || 0;
                const unitPrice = line.price_unit || line.price || 0;
                const discount = line.discount || 0;
                price = qty * unitPrice * (1 - discount / 100);
            }
            if (product?.is_employee_service) {
                employeeAmount += price;
            } else if (product?.is_delivery_product) {
                deliveryAmount += price;
            }
        });
        
        // Get partner
        const partner = order?.partner || order?.customer || (order?.getPartner && order.getPartner()) || null;
        
        if (!partner) {
            console.warn("[PLEDGE] No partner found for pledge order");
            return null;
        }
        
        const pledgeProducts = pledgeInfo.pledgeProductIds;
        
        const employeeLine = lines.find(l => {
            const product = l.product || l.product_id;
            return product?.is_employee_service;
        });
        const employeeProductId = employeeLine ? (employeeLine.product?.id || employeeLine.product_id?.id || null) : null;
        
        const deliveryLine = lines.find(l => {
            const product = l.product || l.product_id;
            return product?.is_delivery_product;
        });
        const deliveryProductId = deliveryLine ? (deliveryLine.product?.id || deliveryLine.product_id?.id || null) : null;
        
        return {
            partner_id: partner.id,
            case_type: caseType,
            pledge_amount: pledgeAmount,
            employee_amount: employeeAmount,
            delivery_amount: deliveryAmount,
            pledge_products: pledgeProducts,
            pledge_line_details: pledgeInfo.pledgeDetails,
            employee_product_id: employeeProductId,
            delivery_product_id: deliveryProductId,
        };
    },

    async createPledgeRecord(order) {
        console.log("[PLEDGE] createPledgeRecord called");
        console.log("[PLEDGE] Order:", order);
        console.log("[PLEDGE] Order pledgeData:", order.pledgeData);
        
        try {
            // Wait a bit for order to be synced and get server ID
            console.log("[PLEDGE] Waiting for order to sync...");
            await new Promise(resolve => setTimeout(resolve, 1500));
            
            // Get the order server ID after it's synced
            const orderId = order.server_id || order.id;
            console.log("[PLEDGE] Order server_id:", order.server_id);
            console.log("[PLEDGE] Order id:", order.id);
            console.log("[PLEDGE] Using orderId:", orderId);
            
            if (!orderId) {
                console.error("[PLEDGE] ⚠️ Order not synced yet, pledge creation skipped");
                this.notification.add(
                    _t("Order not synced, pledge record not created"),
                    { type: "warning" }
                );
                return null;
            }

            if (!order.pledgeData) {
                console.error("[PLEDGE] No pledgeData found on order!");
                return null;
            }

            const pledgeData = {
                pos_order_id: orderId,
                pos_config_id: this.pos.config.id,
                partner_id: order.pledgeData.partner_id,
                case_type: order.pledgeData.case_type,
                pledge_amount: order.pledgeData.pledge_amount || 0,
                employee_amount: order.pledgeData.employee_amount || 0,
                delivery_amount: order.pledgeData.delivery_amount || 0,
                pledge_products: order.pledgeData.pledge_products || [],
                employee_product_id: order.pledgeData.employee_product_id || false,
                delivery_product_id: order.pledgeData.delivery_product_id || false,
            };

            console.log("[PLEDGE] Prepared pledge data for backend:", pledgeData);
            console.log("[PLEDGE] Calling pos.advance.order.pledge.create_from_pos...");

            // Use the orm service from setup
            const pledgeId = await this.orm.call(
                "pos.advance.order.pledge",
                "create_from_pos",
                [pledgeData]
            );
            
            console.log("[PLEDGE] ✅ Pledge record created successfully! ID:", pledgeId);
            
            this.notification.add(
                _t("Pledge record created: %s", order.pledgeData.case_type.toUpperCase()),
                { type: "success" }
            );
            
            return pledgeId;
            
        } catch (error) {
            console.error("[PLEDGE] ✗ Error creating pledge record:", error);
            console.error("[PLEDGE] Error details:", error.message, error.stack);
            this.notification.add(
                _t("Failed to create pledge record: %s", error.message || error),
                { type: "danger" }
            );
            throw error;
        }
    },
});

console.log("[PLEDGE] PaymentScreen patch applied");

console.log("[PLEDGE] Module loaded successfully!", PLEDGE_ORDER_BUILD_TAG);
