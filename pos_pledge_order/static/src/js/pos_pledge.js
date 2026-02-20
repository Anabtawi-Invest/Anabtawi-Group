/** @odoo-module */

console.log("[PLEDGE] Module loading started...");

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PledgeListPopup } from "@pos_pledge_order/js/pledge_list_popup";
import { EmployeeSelectionPopup } from "@pos_pledge_order/js/employee_selection_popup";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

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
    async onClickReturnPledge() {
        console.log("[PLEDGE] ========================================");
        console.log("[PLEDGE] Return Pledge button clicked!");
        console.log("[PLEDGE] makeAwaitable available:", typeof makeAwaitable);
        console.log("[PLEDGE] SelectionPopup available:", typeof SelectionPopup);
        console.log("[PLEDGE] this.dialog:", this.dialog);
        console.log("[PLEDGE] ========================================");
        
        try {
            // First, show return type selection
            console.log("[PLEDGE] Step 1: Showing return type selection popup...");
            
            const returnTypeList = [
                { 
                    id: 'employee', 
                    label: _t("Return Employee Pledge"),
                    item: 'employee' 
                },
                { 
                    id: 'customer', 
                    label: _t("Return Customer Pledge"),
                    item: 'customer' 
                },
            ];
            
            console.log("[PLEDGE] Return type list:", returnTypeList);
            console.log("[PLEDGE] About to call makeAwaitable...");
            
            let returnType;
            try {
                console.log("[PLEDGE] Creating return type selection promise...");
                returnType = await new Promise((resolve) => {
                    console.log("[PLEDGE] Adding SelectionPopup to dialog...");
                    this.dialog.add(
                        SelectionPopup,
                        {
                            title: _t("Select Return Type"),
                            list: returnTypeList,
                            getPayload: (response) => {
                                console.log("[PLEDGE] SelectionPopup getPayload called with:", response);
                                resolve(response);
                            },
                        },
                        {
                            onClose: () => {
                                console.log("[PLEDGE] SelectionPopup closed without selection");
                                resolve(null);
                            },
                        }
                    );
                    console.log("[PLEDGE] SelectionPopup added to dialog");
                });
                console.log("[PLEDGE] Promise resolved, returnType:", returnType);
            } catch (popupError) {
                console.error("[PLEDGE] Error in return type selection:", popupError);
                throw popupError;
            }

            console.log("[PLEDGE] Return type selection result:", returnType);
            console.log("[PLEDGE] Return type type:", typeof returnType);

            if (!returnType) {
                console.log("[PLEDGE] ⚠️ No return type selected, cancelling");
                return;
            }

            console.log("[PLEDGE] ✓ Selected return type:", returnType);

            // Show pledge list popup with search (filtered by return_type)
            console.log("[PLEDGE] Showing pledge list popup with return_type:", returnType);
            const selectedPledge = await new Promise((resolve) => {
                this.dialog.add(
                    PledgeListPopup,
                    {
                        returnType: returnType,
                        getPayload: (response) => {
                            console.log("[PLEDGE] PledgeListPopup getPayload called with:", response);
                            resolve(response);
                        },
                    },
                    {
                        onClose: () => {
                            console.log("[PLEDGE] PledgeListPopup closed without selection");
                            resolve(null);
                        },
                    }
                );
            });

            if (!selectedPledge) {
                console.log("[PLEDGE] No pledge selected, cancelling");
                return;
            }

            console.log("[PLEDGE] Selected pledge:", selectedPledge);
            console.log("[PLEDGE] Return type:", returnType);

            // Confirm return
            const returnTypeLabel = returnType === 'employee' 
                ? _t("Employee Pledge") 
                : _t("Customer Pledge");
            
            const confirmTitle = _t("Return %s - %s for %s (%s)?",
                returnTypeLabel,
                selectedPledge.name,
                selectedPledge.partner_id[1],
                this.pos.env.utils.formatCurrency(selectedPledge.pledge_amount)
            );

            const confirmReturn = await makeAwaitable(this.dialog, SelectionPopup, {
                title: confirmTitle,
                list: [
                    { id: 'yes', label: _t("✓ Yes, Return This Pledge"), item: 'yes' },
                    { id: 'no', label: _t("✗ Cancel"), item: 'no' },
                ],
            });

            if (!confirmReturn || confirmReturn !== 'yes') {
                console.log("[PLEDGE] User cancelled return");
                return;
            }

            // Store return type for later use (will be used in backend logic)
            // Pass return_type as context to backend method
            console.log("[PLEDGE] Calling action_return_pledge for ID:", selectedPledge.id, "Type:", returnType);
            
            await this.env.services.orm.call(
                "pos.pledge",
                "action_return_pledge",
                [[selectedPledge.id]],
                { context: { return_type: returnType } }
            );
            console.log("[PLEDGE] action_return_pledge completed successfully");

            this.notification.add(
                _t("Pledge returned successfully. Reversal entry created."),
                { type: "success" }
            );

        } catch (error) {
            console.error("[PLEDGE] Error returning pledge:", error);
            this.notification.add(
                error.message || _t("Failed to return pledge"),
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
        // Initialize employee fields
        this.employee_id = vals?.employee_id || null;
        this.employee_name = vals?.employee_name || null;
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        // Only send employee_id to backend (employee_name is not a field in pos.order model)
        if (this.employee_id) {
            data.employee_id = this.employee_id;
        }
        console.log("[PLEDGE] Serializing order with employee_id:", this.employee_id);
        return data;
    },
});

console.log("[PLEDGE] PosOrder patch applied");

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
        // Get base receipt data
        const receiptData = order.export_for_printing();
        const lines = order.getOrderlines ? order.getOrderlines() : order.lines || [];
        receiptData.pricelist_name = getOrderPricelistName(order, this.pos);
        
        console.log("[PLEDGE] Preparing receipt data for order");
        
        // Add pledge information to each orderline for QWeb template
        receiptData.orderlines.forEach((receiptLine, index) => {
            const orderline = lines[index];
            if (orderline) {
                const product = orderline.product || orderline.product_id;
                // Add pledge properties to receipt line
                receiptLine.has_pledge = product?.has_pledge || false;
                receiptLine.pledge_amount = product?.pledge_amount || 0;
                receiptLine.is_employee_service = product?.is_employee_service || false;
            }
        });
        
        // Calculate total pledge amount for the receipt
        let totalPledgeAmount = 0;
        const pledgeDetails = [];
        
        lines.forEach(line => {
            const product = line.product || line.product_id;
            if (product?.has_pledge === true) {
                const pledgeAmount = product.pledge_amount || 0;
                const quantity = line.get_quantity ? line.get_quantity() : line.qty;
                const lineTotal = pledgeAmount * quantity;
                totalPledgeAmount += lineTotal;
                
                pledgeDetails.push({
                    product_name: product.display_name || product.name,
                    pledge_amount: pledgeAmount,
                    quantity: quantity,
                    total: lineTotal
                });
            }
        });
        
        // Add pledge information to receipt data
        receiptData.pledgeDetails = pledgeDetails;
        receiptData.totalPledgeAmount = totalPledgeAmount;
        receiptData.hasPledgeProducts = pledgeDetails.length > 0;
        
        console.log("[PLEDGE] Pledge details:", pledgeDetails.length, "items, total:", totalPledgeAmount);

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
        return lines.some(line => {
            const product = line.product || line.product_id;
            return product?.has_pledge || 
                   product?.is_employee_service;
        });
    },

    _preparePledgeData(order) {
        const lines = order.getOrderlines ? order.getOrderlines() : order.lines || [];
        
        // Detect case type
        const hasEmployee = lines.some(l => {
            const product = l.product || l.product_id;
            return product?.is_employee_service;
        });
        const hasPledge = lines.some(l => {
            const product = l.product || l.product_id;
            return product?.has_pledge;
        });
        const hasDelivery = lines.some(l => {
            const product = l.product || l.product_id;
            return product?.is_delivery_product;
        });
        
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
        
        // Calculate amounts
        let pledgeAmount = 0;
        let employeeAmount = 0;
        let deliveryAmount = 0;
        
        console.log("[PLEDGE] Calculating amounts from", lines.length, "lines");
        
        lines.forEach((line, idx) => {
            const product = line.product || line.product_id;
            console.log(`[PLEDGE] Line ${idx}:`, {
                product_name: product?.display_name || product?.name,
                has_pledge: product?.has_pledge,
                is_employee_service: product?.is_employee_service,
                is_delivery_product: product?.is_delivery_product,
                pledge_amount: product?.pledge_amount,
            });
            
            // Get price - try multiple methods for Odoo 19 compatibility
            let price = 0;
            
            if (typeof line.get_price_with_tax === 'function') {
                price = line.get_price_with_tax();
                console.log(`[PLEDGE]   -> get_price_with_tax(): ${price}`);
            } else if (typeof line.getPriceWithTax === 'function') {
                price = line.getPriceWithTax();
                console.log(`[PLEDGE]   -> getPriceWithTax(): ${price}`);
            } else if (typeof line.get_all_prices === 'function') {
                const prices = line.get_all_prices();
                price = prices?.priceWithTax || prices?.price_with_tax || 0;
                console.log(`[PLEDGE]   -> get_all_prices(): ${JSON.stringify(prices)}`);
            } else if (line.price_subtotal_incl !== undefined) {
                price = line.price_subtotal_incl;
                console.log(`[PLEDGE]   -> price_subtotal_incl: ${price}`);
            } else if (line.price_with_tax !== undefined) {
                price = line.price_with_tax;
                console.log(`[PLEDGE]   -> price_with_tax: ${price}`);
            } else {
                // Fallback: calculate manually
                const qty = line.quantity || line.qty || 0;
                const unitPrice = line.price_unit || line.price || 0;
                const discount = line.discount || 0;
                price = qty * unitPrice * (1 - discount / 100);
                console.log(`[PLEDGE]   -> Manual calc: ${qty} * ${unitPrice} * (1 - ${discount}/100) = ${price}`);
                console.log(`[PLEDGE]   -> Note: This is without tax! Line object:`, line);
            }
            
            console.log(`[PLEDGE]   -> Final price for line: ${price}`);
            
            if (product?.has_pledge) {
                const lineAmount = product.pledge_amount || price;
                pledgeAmount += lineAmount;
                console.log(`[PLEDGE]   -> Adding ${lineAmount} to pledgeAmount (total: ${pledgeAmount})`);
            } else if (product?.is_employee_service) {
                employeeAmount += price;
                console.log(`[PLEDGE]   -> Adding ${price} to employeeAmount (total: ${employeeAmount})`);
            } else if (product?.is_delivery_product) {
                deliveryAmount += price;
                console.log(`[PLEDGE]   -> Adding ${price} to deliveryAmount (total: ${deliveryAmount})`);
            }
        });
        
        console.log("[PLEDGE] Final calculated amounts:", {
            pledgeAmount,
            employeeAmount,
            deliveryAmount
        });
        
        // Get partner
        const partner = order?.partner || order?.customer || (order?.getPartner && order.getPartner()) || null;
        
        if (!partner) {
            console.warn("[PLEDGE] No partner found for pledge order");
            return null;
        }
        
        // Prepare pledge products data
        const pledgeProducts = lines
            .filter(l => {
                const product = l.product || l.product_id;
                return product?.has_pledge;
            })
            .map(l => {
                const product = l.product || l.product_id;
                return product.id;
            });
        
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
            console.log("[PLEDGE] Calling pos.pledge.create_from_pos...");

            // Use the orm service from setup
            const pledgeId = await this.orm.call(
                "pos.pledge",
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

// =============================================================================
// 4. Patch ReceiptScreen to add Print Customer Receipt functionality
// =============================================================================
patch(ReceiptScreen.prototype, {
    setup() {
        super.setup(...arguments);
        console.log("[PLEDGE] ========================================");
        console.log("[PLEDGE] ReceiptScreen setup complete!");
        console.log("[PLEDGE] printFullReceipt available:", typeof this.printFullReceipt);
        console.log("[PLEDGE] printCustomerReceipt available:", typeof this.printCustomerReceipt);
        console.log("[PLEDGE] ========================================");
    },
    
    /**
     * Override receiptData getter to add pledge information (as metadata, not as lines)
     */
    get receiptData() {
        const data = super.receiptData;
        
        console.log("[PLEDGE] receiptData getter called");
        console.log("[PLEDGE] Super receipt data:", data);
        
        if (!this.currentOrder) {
            console.log("[PLEDGE] No current order");
            return data;
        }
        
        console.log("[PLEDGE] Adding pledge info to receipt data");
        
        const lines = this.currentOrder.lines || [];
        
        // Calculate pledge details for separate section in QWeb
        let totalPledgeAmount = 0;
        const pledgeDetails = [];
        
        lines.forEach(line => {
            const product = line.get_product();
            if (product?.has_pledge === true) {
                const pledgeAmount = product.pledge_amount || 0;
                const quantity = line.get_quantity();
                const lineTotal = pledgeAmount * quantity;
                totalPledgeAmount += lineTotal;
                
                pledgeDetails.push({
                    product_name: product.display_name || product.name,
                    pledge_amount: pledgeAmount,
                    quantity: quantity,
                    total: lineTotal
                });
                
                console.log("[PLEDGE] Pledge detail:", product.display_name, "=", lineTotal);
            }
        });
        
        // Add pledge information to receipt data (for QWeb template)
        data.pledgeDetails = pledgeDetails;
        data.totalPledgeAmount = totalPledgeAmount;
        data.hasPledgeProducts = pledgeDetails.length > 0;
        
        console.log("[PLEDGE] Total pledge amount:", totalPledgeAmount);
        console.log("[PLEDGE] Pledge details count:", pledgeDetails.length);
        console.log("[PLEDGE] ✅ Final receipt data with pledge:", data);
        console.log("[PLEDGE] ✅ pledgeDetails:", data.pledgeDetails);
        console.log("[PLEDGE] ✅ totalPledgeAmount:", data.totalPledgeAmount);
        
        return data;
    },
    
    /**
     * Print full receipt with pledge section
     * Hides delivery products if employee service exists
     */
    async printFullReceipt() {
        console.log("[PLEDGE] ========================================");
        console.log("[PLEDGE] 🎯 printFullReceipt() METHOD CALLED!");
        console.log("[PLEDGE] ========================================");
        
        try {
            const order = this.currentOrder;
            
            if (!order) {
                console.log("[PLEDGE] ❌ No order found");
                this.notification.add(_t("No order found"), { type: "warning" });
                return;
            }

            console.log("[PLEDGE] ✅ Order found:", order.name);
            console.log("[PLEDGE] Starting full receipt printing...");
            
            const lines = order.lines || [];
            console.log("[PLEDGE] Total lines in order:", lines.length);
            
            // Hide pledge section when an employee is selected, even without employee service lines.
            const hasSelectedEmployee = !!(order.employee_id && (order.employee_id.id || order.employee_id));

            // Check if there's an employee service
            const hasEmployeeService = lines.some(line => {
                const product = line.product_id;
                const isEmp = product?.is_employee_service === true;
                if (isEmp) {
                    console.log("[PLEDGE] 👨‍💼 Found employee service:", product?.display_name || product?.name);
                }
                return isEmp;
            });
            const hidePledgeByEmployee = hasEmployeeService || hasSelectedEmployee;
            
            console.log("[PLEDGE] Has employee service:", hasEmployeeService);
            console.log("[PLEDGE] Has selected employee:", hasSelectedEmployee);
            console.log("[PLEDGE] Hide pledge section:", hidePledgeByEmployee);
            console.log("[PLEDGE] Will filter delivery products:", hidePledgeByEmployee);
            
            // Prepare receipt data
            const company = this.pos.company;
            const cashierName = order.getCashierName ? order.getCashierName() : (order.employee_id?.name || 'Cashier');
            const orderPricelist =
                (typeof order.get_pricelist === "function" && order.get_pricelist()) ||
                (typeof order.getPricelist === "function" && order.getPricelist()) ||
                order.pricelist ||
                order.pricelist_id ||
                this.pos?.config?.pricelist_id ||
                this.pos?.default_pricelist;
            const pricelistName =
                orderPricelist?.name ||
                (Array.isArray(orderPricelist) ? orderPricelist[1] : null) ||
                "";
            
            const receiptData = {
                company: {
                    name: company.name,
                    street: company.street,
                    phone: company.phone,
                    vat: company.vat,
                    email: company.email,
                },
                cashier: cashierName,
                name: order.name,
                date: order.date_order ? new Date(order.date_order).toLocaleString() : new Date().toLocaleString(),
                partner: order.partner_id ? {
                    name: order.partner_id.name,
                    phone: order.partner_id.phone,
                } : null,
                pricelist_name: pricelistName,
                total_with_tax: this.env.utils.formatCurrency(order.amount_total || 0, false),
                change: this.env.utils.formatCurrency(0, false),
            };
            
            // Build orderlines - filter delivery if employee service exists
            const fullOrderlines = [];
            let total = 0;
            
            console.log("[PLEDGE] Building orderlines...");
            
            lines.forEach((line, index) => {
                const product = line.product_id;
                console.log(`[PLEDGE] Line ${index + 1}:`, product?.display_name || product?.name);
                console.log(`[PLEDGE]   - is_employee_service:`, product?.is_employee_service);
                console.log(`[PLEDGE]   - is_delivery_product:`, product?.is_delivery_product);
                
                // If employee service exists, skip delivery products
                if (hidePledgeByEmployee && product?.is_delivery_product) {
                    console.log("[PLEDGE] 🚫 SKIPPING delivery product (employee exists):", product.display_name || product.name);
                    return;
                }
                
                const quantity = line.qty;
                const unitPrice = line.price_unit;
                const priceWithTax = line.price_subtotal_incl;
                
                fullOrderlines.push({
                    product_name: product.display_name || product.name,
                    quantity: quantity.toString(),
                    price: this.env.utils.formatCurrency(unitPrice, false),
                    price_display: this.env.utils.formatCurrency(priceWithTax, false),
                    is_employee_service: product?.is_employee_service || false,
                    is_delivery_product: product?.is_delivery_product || false,
                });
                
                total += priceWithTax;
            });
            
            receiptData.orderlines = fullOrderlines;
            receiptData.total = this.env.utils.formatCurrency(total, false);
            
            // Calculate pledge section
            let pledgeTotal = 0;
            const pledgeLines = [];
            
            lines.forEach(line => {
                const product = line.product_id;
                if (product?.has_pledge && !hidePledgeByEmployee) {
                    const pledgeAmt = (product.pledge_amount || 0) * line.qty;
                    pledgeTotal += pledgeAmt;
                    pledgeLines.push({
                        name: product.display_name || product.name,
                        amount: pledgeAmt
                    });
                }
            });
            
            receiptData.hasPledge = pledgeTotal > 0;
            receiptData.pledgeLines = pledgeLines;
            receiptData.pledgeTotal = this.env.utils.formatCurrency(pledgeTotal, false);
            
            console.log("[PLEDGE] ========================================");
            console.log("[PLEDGE] 📋 Final Receipt Data:");
            console.log("[PLEDGE]   - Total orderlines:", fullOrderlines.length);
            console.log("[PLEDGE]   - Has pledge:", receiptData.hasPledge);
            console.log("[PLEDGE]   - Orderlines:", fullOrderlines);
            console.log("[PLEDGE] ========================================");
            
            // Build and print HTML
            const html = this._buildFullReceiptHtml(receiptData);
            console.log("[PLEDGE] 🖨️ Calling printHtmlReceipt...");
            printHtmlReceipt(html, 'Full Receipt');
            
            this.notification.add(_t("Full receipt printed successfully"), { type: "success" });
            console.log("[PLEDGE] ✅ Full receipt printed successfully!");
            
        } catch (error) {
            console.error("[PLEDGE] Error printing full receipt:", error);
            this.notification.add(
                error.message || _t("Failed to print full receipt"),
                { type: "danger" }
            );
        }
    },
    
    /**
     * Build full receipt HTML
     */
_buildFullReceiptHtml(receiptData) {
    let html = `
        <div class="pos-receipt">
            <div class="pos-receipt-header text-center mb-3">
                <h2>PLEDGE RECEIPT</h2>
                <div class="mb-2">${receiptData.company.name || ''}</div>
                ${receiptData.company.street ? `<div>${receiptData.company.street}</div>` : ''}
                ${receiptData.company.phone ? `<div>Tel: ${receiptData.company.phone}</div>` : ''}
            </div>

            <div class="cashier mb-2">
                <div>Cashier: ${receiptData.cashier}</div>
                <div>Order: ${receiptData.name}</div>
                <div>Date: ${receiptData.date}</div>
                ${receiptData.pricelist_name ? `<div>Pricelist: ${receiptData.pricelist_name}</div>` : ''}
            </div>

            ${receiptData.partner ? `
                <div class="partner-info mb-2">
                    <div><strong>Customer: ${receiptData.partner.name}</strong></div>
                    ${receiptData.partner.phone ? `<div>Phone: ${receiptData.partner.phone}</div>` : ''}
                </div>
            ` : ''}

            <hr/>
    `;

    if (receiptData.hasPledge) {
        html += `
            <div style="margin-top: 20px; padding-top: 15px;">
                <h4 style="text-align: center; font-weight: bold; text-decoration: underline;">
                    معلومات الرهن / Pledge Information
                </h4>
                <table style="width: 100%; margin: 10px 0;">
        `;

        receiptData.pledgeLines.forEach(pline => {
            html += `
                    <tr>
                        <td>${pline.name}</td>
                        <td style="text-align: right;">
                            ${this.env.utils.formatCurrency(pline.amount, false)}
                        </td>
                    </tr>
            `;
        });

        html += `
                    <tr style="border-top: 2px solid #000;">
                        <td><strong>إجمالي الرهن:</strong></td>
                        <td style="text-align: right;">
                            <strong>${receiptData.pledgeTotal}</strong>
                        </td>
                    </tr>
                </table>
                <div style="text-align: center; font-size: 0.85em; color: #666; font-style: italic; border-top: 1px dashed #999; padding-top: 8px;">
                    ⚠️ هذا المبلغ سيُرد عند إعادة المنتج<br/>
                    This amount will be refunded upon product return
                </div>
            </div>
        `;
    } else {
        html += `
            <div style="text-align:center; margin-top:20px;">
                No pledge items found.
            </div>
        `;
    }

    html += `
            <div class="text-center mt-4">
                <div>Thank you!</div>
            </div>
        </div>
    `;

    return html;
},
    
    /**
     * Print customer receipt (filtered - no pledge products, no virtual pledge lines)
     */
    async printCustomerReceipt() {
        try {
            const order = this.currentOrder;
            
            if (!order) {
                this.notification.add(_t("No order found"), { type: "warning" });
                return;
            }

            console.log("[PLEDGE] Printing customer receipt from Receipt Screen");
            console.log("[PLEDGE] Order data:", order);

            // Prepare receipt data manually from order properties
            const company = this.pos.company;
            const cashierName = order.getCashierName ? order.getCashierName() : (order.employee_id?.name || 'Cashier');
            const pricelistName = getOrderPricelistName(order, this.pos);
            
            const receiptData = {
                company: {
                    name: company.name,
                    street: company.street,
                    phone: company.phone,
                    vat: company.vat,
                    email: company.email,
                },
                cashier: cashierName,
                name: order.name,
                date: order.date_order ? new Date(order.date_order).toLocaleString() : new Date().toLocaleString(),
                partner: order.partner_id ? {
                    name: order.partner_id.name,
                    phone: order.partner_id.phone,
                } : null,
                pricelist_name: pricelistName,
                total_with_tax: this.env.utils.formatCurrency(order.amount_total || order.priceIncl || 0, false),
                change: this.env.utils.formatCurrency(0, false), // No change on completed orders
            };

            // Get order lines from the order
            const lines = order.lines || [];
            
            console.log("[PLEDGE] Found order lines:", lines.length);

            // Create customer orderlines - EXCLUDE employee service and delivery products
            const customerLines = [];
            let customerTotal = 0;
            
            lines.forEach(line => {
                const product = line.product_id;
                
                // Skip employee service products (always hidden)
                if (product?.is_employee_service) {
                    console.log("[PLEDGE] Skipping employee service product:", product.display_name || product.name);
                    return;
                }
                
                // Skip delivery products (always hidden)
                if (product?.is_delivery_product) {
                    console.log("[PLEDGE] Skipping delivery product:", product.display_name || product.name);
                    return;
                }
                
                console.log("[PLEDGE] Adding line to customer receipt:", product?.display_name || product?.name);
                
                const quantity = line.qty;
                const unitPrice = line.price_unit;
                const priceWithTax = line.price_subtotal_incl;
                
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
            
            console.log("[PLEDGE] Customer orderlines:", receiptData.customerOrderlines?.length || 0);
            console.log("[PLEDGE] Customer total:", receiptData.customer_total);

            if (!receiptData.customerOrderlines || receiptData.customerOrderlines.length === 0) {
                this.notification.add(
                    _t("This order only contains pledge/employee/delivery items. No customer items to print."),
                    { type: "info" }
                );
                return;
            }

            // Render and print customer receipt
            // Build the receipt HTML manually using template literals
            const html = this._buildCustomerReceiptHtml(receiptData);
            
            // Print using helper function
            printHtmlReceipt(html, 'Customer Receipt');

            this.notification.add(_t("Customer receipt printed successfully"), { type: "success" });
            console.log("[PLEDGE] ✅ Customer receipt printed from Receipt Screen");

        } catch (error) {
            console.error("[PLEDGE] Error printing customer receipt:", error);
            this.notification.add(
                error.message || _t("Failed to print customer receipt"),
                { type: "danger" }
            );
        }
    },

    /**
     * Build customer receipt HTML manually
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

        // Add customer orderlines
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
});

console.log("[PLEDGE] ReceiptScreen patch applied");
console.log("[PLEDGE] Module loaded successfully!");
