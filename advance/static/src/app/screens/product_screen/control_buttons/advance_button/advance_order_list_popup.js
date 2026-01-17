/** @odoo-module **/

import {Component, useState, onMounted} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {usePos} from "@point_of_sale/app/hooks/pos_hook";
import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";
import {EmployeeSelectionPopup} from "@pos_pledge/js/employee_selection_popup";

export class AdvanceOrderListPopup extends Component {
    static template = "pos_advance.AdvanceOrderListPopup";
    static components = {Dialog};
    static props = {close: Function};

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.pos = usePos();

        this.state = useState({
            advances: [],
            selectedAdvance: null,
            search: "",
            paymentType: "cash",
            selectedEmployee: null,
        });

        onMounted(() => this._loadAdvances());
    }

    // ==================================
    // LOAD ADVANCE PAYMENTS
    // ==================================
    async _loadAdvances() {
        // Filter by pickup_pos_id matching current POS
        const advances = await this.orm.searchRead(
            "pos.advance.payment",
            [
                ["state", "=", "paid"],
                ["invoice_id", "=", false],
                ["pickup_pos_id", "=", this.pos.config.id],  // Filter by pickup location
            ],
            [
                "id",
                "name",
                "partner_id",
                "total_expected",
                "amount_paid",
                "remaining_amount",
                "due_date",
                "pickup_pos_id",
            ]
        );
        
        // Load partner phone numbers separately
        const partnerIds = [...new Set(advances.map(adv => adv.partner_id?.[0]).filter(Boolean))];
        if (partnerIds.length > 0) {
            const partners = await this.orm.searchRead(
                "res.partner",
                [["id", "in", partnerIds]],
                ["id", "phone"]
            );
            
            // Create a map of partner_id -> phone
            const partnerPhoneMap = {};
            partners.forEach(partner => {
                partnerPhoneMap[partner.id] = partner.phone || '';
            });
            
            // Add phone to each advance
            advances.forEach(adv => {
                if (adv.partner_id && adv.partner_id[0]) {
                    adv.partner_phone = partnerPhoneMap[adv.partner_id[0]] || '';
                }
            });
        }
        
        this.state.advances = advances;
    }

    // ==================================
    // 🔍 SEARCH HANDLER
    // ==================================
    onSearchInput(ev) {
        this.state.search = (ev.target.value || "").toLowerCase();
    }

    // ==================================
    // 🔍 FILTERED ADVANCES
    // ==================================
    get filteredAdvances() {
        if (!this.state.search) {
            return this.state.advances;
        }

        const searchLower = this.state.search.toLowerCase();
        
        return this.state.advances.filter(adv => {
            // Search by advance number
            if (adv.name?.toLowerCase().includes(searchLower)) {
                return true;
            }
            // Search by customer name
            if (adv.partner_id?.[1]?.toLowerCase().includes(searchLower)) {
                return true;
            }
            // Search by customer phone number
            const phone = adv.partner_phone || '';
            if (phone && phone.toString().toLowerCase().includes(searchLower)) {
                return true;
            }
            return false;
        });
    }

    onSearchKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }

        ev.preventDefault();

        if (!this.filteredAdvances.length) {
            this.notification.add(
                _t("No advance found."),
                {type: "warning"}
            );
            return;
        }

        const first = this.filteredAdvances[0];
        console.log("[ADVANCE] Enter pressed, opening:", first);

        this.selectAdvance(first);
    }

    // ==================================
    // LOAD PRODUCTS (advance lines)
    // ==================================
    async _loadAdvanceLines(advanceId) {
        const lines = await this.orm.searchRead(
            "pos.advance.line",
            [["advance_id", "=", advanceId]],
            ["product_id", "qty", "price_unit", "subtotal"]
        );
        
        // Load product details to check for is_employee_service
        const productIds = lines.map(l => l.product_id?.[0]).filter(Boolean);
        if (productIds.length > 0) {
            const products = await this.orm.searchRead(
                "product.product",
                [["id", "in", productIds]],
                ["id", "is_employee_service"]
            );
            
            // Create a map of product_id -> is_employee_service
            const productServiceMap = {};
            products.forEach(product => {
                productServiceMap[product.id] = product.is_employee_service || false;
            });
            
            // Add is_employee_service to each line
            lines.forEach(line => {
                if (line.product_id && line.product_id[0]) {
                    line.is_employee_service = productServiceMap[line.product_id[0]] || false;
                } else {
                    line.is_employee_service = false;
                }
            });
        }
        
        return lines;
    }

    // ==================================
    // SELECT ADVANCE
    // ==================================
    async selectAdvance(adv) {
        const customer = adv.partner_id?.[1];
        const lines = await this._loadAdvanceLines(adv.id);

        // Check if any product has is_employee_service
        const hasEmployeeService = lines.some(l => l.is_employee_service === true);

        this.state.selectedAdvance = {
            id: adv.id,
            name: adv.name,
            customer: customer,
            total: adv.total_expected,
            paid: adv.amount_paid,
            remaining: adv.remaining_amount,
            hasEmployeeService: hasEmployeeService,
            products: lines.map(l => ({
                product_id: l.product_id?.[0],
                product_name: l.product_id?.[1],
                qty: l.qty,
                price_unit: l.price_unit,
                subtotal: l.subtotal,
                is_employee_service: l.is_employee_service || false,
            })),
        };

        // Reset employee selection when selecting a new advance
        this.state.selectedEmployee = null;

        console.log("[ADVANCE] selectedAdvance =", this.state.selectedAdvance);
        console.log("[ADVANCE] hasEmployeeService =", hasEmployeeService);
    }

    // ==================================
    // SELECT EMPLOYEE
    // ==================================
    async selectEmployee() {
        try {
            const selectedEmployee = await new Promise((resolve) => {
                this.dialog.add(EmployeeSelectionPopup, {
                    getPayload: (payload) => {
                        resolve(payload);
                    },
                });
            });

            if (selectedEmployee) {
                this.state.selectedEmployee = selectedEmployee;
                this.notification.add(
                    _t("Employee selected: %s", selectedEmployee.name),
                    { type: "success" }
                );
            }
        } catch (error) {
            console.error("[ADVANCE] Error selecting employee:", error);
            this.notification.add(
                error.message || _t("Failed to select employee"),
                { type: "danger" }
            );
        }
    }

    // ==================================
    // CREATE INVOICE
    // ==================================
    async createInvoice() {
        if (!this.state.selectedAdvance) {
            this.notification.add(
                _t("Please select an advance first."),
                {type: "warning"}
            );
            return;
        }

        // Check if employee service is required
        if (this.state.selectedAdvance.hasEmployeeService && !this.state.selectedEmployee) {
            this.notification.add(
                _t("Please select an employee. This order contains employee service products."),
                {type: "warning"}
            );
            return;
        }

        try {
            await this.orm.call(
                "pos.advance.payment",
                "action_create_invoice",
                [[this.state.selectedAdvance.id], {
                    payment_type: this.state.paymentType,
                    employee_id: this.state.selectedEmployee?.id || false,
                }]
            );

            this.notification.add(
                _t("Invoice created successfully."),
                {type: "success"}
            );

            // Print receipt with all products
            this._printReceipt();

            this.props.close();

        } catch (error) {
            console.error(error);
            this.notification.add(
                error.message || _t("Failed to create invoice."),
                {type: "danger"}
            );
        }
    }

    // ==================================
    // PRINT RECEIPT
    // ==================================
    _printReceipt() {
        if (!this.state.selectedAdvance) {
            return;
        }

        const advance = this.state.selectedAdvance;
        const company = this.pos.company;

        // Build receipt HTML
        let receiptHtml = `
            <div class="pos-receipt">
                <div class="text-center mb-3">
                    <h3>${company.name || 'Receipt'}</h3>
                    ${company.street ? `<div>${company.street}</div>` : ''}
                    ${company.phone ? `<div>Tel: ${company.phone}</div>` : ''}
                </div>
                
                <div class="mb-3">
                    <div><strong>Advance #:</strong> ${advance.name}</div>
                    <div><strong>Customer:</strong> ${advance.customer}</div>
                    <div><strong>Date:</strong> ${new Date().toLocaleString()}</div>
                    <div><strong>Payment Method:</strong> ${this.state.paymentType === 'cash' ? 'Cash' : 'Card'}</div>
                </div>
                
                <div class="table-borderless mb-3">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="border-bottom: 2px solid #000;">
                                <th style="text-align: left; padding: 5px;">Product</th>
                                <th style="text-align: center; padding: 5px;">Qty</th>
                                <th style="text-align: right; padding: 5px;">Price</th>
                                <th style="text-align: right; padding: 5px;">Total</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        let totalAmount = 0;
        advance.products.forEach(product => {
            const lineTotal = parseFloat(product.subtotal) || 0;
            totalAmount += lineTotal;
            receiptHtml += `
                <tr style="border-bottom: 1px solid #ddd;">
                    <td style="padding: 5px;">${product.product_name}</td>
                    <td style="text-align: center; padding: 5px;">${product.qty}</td>
                    <td style="text-align: right; padding: 5px;">${this.pos.env.utils.formatCurrency(product.price_unit, false)}</td>
                    <td style="text-align: right; padding: 5px;">${this.pos.env.utils.formatCurrency(lineTotal, false)}</td>
                </tr>
            `;
        });

        receiptHtml += `
                        </tbody>
                    </table>
                </div>
                
                <div class="text-end mb-3">
                    <div><strong>Total:</strong> ${this.pos.env.utils.formatCurrency(totalAmount, false)}</div>
                    <div><strong>Paid:</strong> ${this.pos.env.utils.formatCurrency(advance.paid, false)}</div>
                    <div><strong>Remaining:</strong> ${this.pos.env.utils.formatCurrency(advance.remaining, false)}</div>
                </div>
                
                <div class="text-center mt-4">
                    <div>Thank you for your purchase!</div>
                </div>
            </div>
        `;

        // Print receipt
        this._printHtmlReceipt(receiptHtml, 'Advance Order Receipt');
    }

    // ==================================
    // PRINT HTML RECEIPT
    // ==================================
    _printHtmlReceipt(html, title = 'Receipt') {
        const printWindow = window.open('', '_blank', 'width=300,height=600');
        printWindow.document.write(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>${title}</title>
                <style>
                    body { font-family: monospace; width: 300px; margin: 20px auto; padding: 10px; }
                    .pos-receipt { padding: 10px; }
                    .text-center { text-align: center; }
                    .text-end { text-align: right; }
                    .mb-1, .mb-2, .mb-3, .mt-3, .mt-4 { margin-bottom: 10px; }
                    .table-borderless { width: 100%; border-top: 2px solid #000; padding-top: 10px; }
                    table { width: 100%; border-collapse: collapse; }
                    th, td { padding: 5px; }
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
}

window.AdvanceOrderListPopup = AdvanceOrderListPopup;
