/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class PledgeListPopup extends Component {
    static template = "pos_pledge.PledgeListPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        returnType: { type: String, optional: true }, // 'employee' or 'customer'
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.pos = usePos();

        this.state = useState({
            pledges: [],
            selectedPledge: null,
            search: "",
            selectedPledgeDetails: null,
        });

        onMounted(() => this._loadPledges());
    }

    // ==================================
    // LOAD ACTIVE PLEDGES (FILTERED BY RETURN TYPE)
    // ==================================
    async _loadPledges() {
        const returnType = this.props.returnType || 'customer';
        console.log("[PLEDGE] Loading active pledges for popup (return_type:", returnType, ")...");
        
        try {
            // Build domain based on return_type
            const domain = [['state', '=', 'active']];
            
            if (returnType === 'employee') {
                // Employee pledges: must have employee_id
                domain.push(['employee_id', '!=', false]);
                console.log("[PLEDGE] Filtering for employee pledges (with employee_id)");
            } else {
                // Customer pledges: must NOT have employee_id
                domain.push(['employee_id', '=', false]);
                console.log("[PLEDGE] Filtering for customer pledges (without employee_id)");
            }
            
            this.state.pledges = await this.orm.searchRead(
                "pos.pledge",
                domain,
                ['id', 'name', 'partner_id', 'pledge_amount', 'employee_amount', 'delivery_amount', 'case_type', 'create_date', 'employee_id', 'state', 'return_date', 'pos_order_id'],
                { order: 'create_date desc' }
            );
            
            // Load employee names for each pledge
            const employeeIds = this.state.pledges
                .map(p => p.employee_id && p.employee_id[0])
                .filter(id => id);
            
            if (employeeIds.length > 0) {
                const employees = await this.orm.searchRead(
                    "hr.employee",
                    [['id', 'in', employeeIds]],
                    ['id', 'name'],
                    {}
                );
                
                // Create a map of employee_id -> employee_name
                const employeeMap = {};
                employees.forEach(emp => {
                    employeeMap[emp.id] = emp.name;
                });
                
                // Add employee_name to each pledge
                this.state.pledges = this.state.pledges.map(pledge => {
                    if (pledge.employee_id && pledge.employee_id[0]) {
                        pledge.employee_name = employeeMap[pledge.employee_id[0]] || '';
                    } else {
                        pledge.employee_name = '';
                    }
                    return pledge;
                });
            }
            
            // Load partner phone numbers for search
            const partnerIds = [...new Set(this.state.pledges.map(p => p.partner_id?.[0]).filter(Boolean))];
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
                
                // Add phone to each pledge
                this.state.pledges = this.state.pledges.map(pledge => {
                    if (pledge.partner_id && pledge.partner_id[0]) {
                        pledge.partner_phone = partnerPhoneMap[pledge.partner_id[0]] || '';
                    } else {
                        pledge.partner_phone = '';
                    }
                    return pledge;
                });
            }
            console.log("[PLEDGE] Loaded", this.state.pledges.length, "active pledges for return_type:", returnType);
        } catch (error) {
            console.error("[PLEDGE] Error loading pledges:", error);
            this.notification.add(
                _t("Failed to load pledges"),
                { type: "danger" }
            );
        }
    }

    // ==================================
    // 🔍 SEARCH HANDLER
    // ==================================
    onSearchInput(ev) {
        this.state.search = (ev.target.value || "").toLowerCase();
        console.log("[PLEDGE] Search updated:", this.state.search);
    }

    // ==================================
    // 🔍 FILTERED PLEDGES
    // ==================================
    get filteredPledges() {
        if (!this.state.search) {
            return this.state.pledges;
        }

        const searchLower = this.state.search.toLowerCase();
        return this.state.pledges.filter(pledge =>
            pledge.name?.toLowerCase().includes(searchLower) ||
            pledge.partner_id?.[1]?.toLowerCase().includes(searchLower) ||
            pledge.employee_name?.toLowerCase().includes(searchLower) ||
            (pledge.partner_phone && pledge.partner_phone.toString().toLowerCase().includes(searchLower))
        );
    }

    // ==================================
    // SEARCH KEYDOWN (Enter to select first)
    // ==================================
    onSearchKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }

        ev.preventDefault();

        if (!this.filteredPledges.length) {
            this.notification.add(
                _t("No pledge found."),
                { type: "warning" }
            );
            return;
        }

        const first = this.filteredPledges[0];
        console.log("[PLEDGE] Enter pressed, selecting first pledge:", first);
        this.selectPledge(first);
    }

    // ==================================
    // SELECT PLEDGE
    // ==================================
    selectPledge(pledge) {
        console.log("[PLEDGE] Pledge selected:", pledge);
        this.props.getPayload(pledge);
        this.props.close();
    }

    // ==================================
    // CANCEL
    // ==================================
    cancel() {
        console.log("[PLEDGE] Pledge selection cancelled");
        this.props.getPayload(null);
        this.props.close();
    }

    // ==================================
    // SHOW PLEDGE DETAILS
    // ==================================
    async showPledgeDetails(pledge) {
        console.log("[PLEDGE] Showing details for pledge:", pledge);
        
        try {
            // Load full pledge details including products
            const pledgeDetails = await this.orm.searchRead(
                "pos.pledge",
                [['id', '=', pledge.id]],
                ['id', 'name', 'partner_id', 'employee_id', 'pledge_amount', 'employee_amount', 'delivery_amount', 
                 'case_type', 'create_date', 'return_date', 'state', 'pledge_products', 'pos_order_id'],
                { limit: 1 }
            );
            
            if (!pledgeDetails || !pledgeDetails.length) {
                this.notification.add(
                    _t("Failed to load pledge details"),
                    { type: "warning" }
                );
                return;
            }
            
            const fullPledge = pledgeDetails[0];
            
            // Load pledge products details
            let products = [];
            if (fullPledge.pledge_products && fullPledge.pledge_products.length > 0) {
                const productIds = fullPledge.pledge_products.map(p => p[0]);
                const productDetails = await this.orm.searchRead(
                    "product.product",
                    [['id', 'in', productIds]],
                    ['id', 'name', 'display_name']
                );
                
                // Get quantities from pos.order lines if available
                if (fullPledge.pos_order_id && fullPledge.pos_order_id[0]) {
                    try {
                        const orderLines = await this.orm.searchRead(
                            "pos.order.line",
                            [['order_id', '=', fullPledge.pos_order_id[0]]],
                            ['product_id', 'qty']
                        );
                        
                        products = productDetails.map(product => {
                            const line = orderLines.find(l => l.product_id && l.product_id[0] === product.id);
                            return {
                                id: product.id,
                                name: product.display_name || product.name,
                                qty: line ? line.qty : 1
                            };
                        });
                    } catch (error) {
                        console.warn("[PLEDGE] Could not load order lines:", error);
                        products = productDetails.map(product => ({
                            id: product.id,
                            name: product.display_name || product.name,
                            qty: 1
                        }));
                    }
                } else {
                    products = productDetails.map(product => ({
                        id: product.id,
                        name: product.display_name || product.name,
                        qty: 1
                    }));
                }
            }
            
            // Combine all details
            this.state.selectedPledgeDetails = {
                ...fullPledge,
                employee_name: pledge.employee_name || '',
                partner_phone: pledge.partner_phone || '',
                products: products
            };
            
            console.log("[PLEDGE] Pledge details loaded:", this.state.selectedPledgeDetails);
        } catch (error) {
            console.error("[PLEDGE] Error loading pledge details:", error);
            this.notification.add(
                _t("Failed to load pledge details: %s", error.message || error),
                { type: "danger" }
            );
        }
    }

    // ==================================
    // FORMAT CURRENCY
    // ==================================
    formatCurrency(amount) {
        return this.pos.env.utils.formatCurrency(amount, false);
    }
}
