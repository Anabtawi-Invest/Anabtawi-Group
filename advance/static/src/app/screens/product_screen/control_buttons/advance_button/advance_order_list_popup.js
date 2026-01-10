/** @odoo-module **/

import {Component, useState, onMounted} from "@odoo/owl";
import {useService} from "@web/core/utils/hooks";
import {Dialog} from "@web/core/dialog/dialog";
import {_t} from "@web/core/l10n/translation";

export class AdvanceOrderListPopup extends Component {
    static template = "pos_advance.AdvanceOrderListPopup";
    static components = {Dialog};
    static props = {close: Function};

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            advances: [],
            selectedAdvance: null,
            search: "",
            paymentType: "cash",
        });

        onMounted(() => this._loadAdvances());
    }

    // ==================================
    // LOAD ADVANCE PAYMENTS
    // ==================================
    async _loadAdvances() {
        this.state.advances = await this.orm.searchRead(
            "pos.advance.payment",
            [
                ["state", "=", "paid"],
                ["invoice_id", "=", false],
            ],
            [
                "id",
                "name",
                "partner_id",
                "total_expected",
                "amount_paid",
                "remaining_amount",
            ]
        );
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

        return this.state.advances.filter(adv =>
            adv.name?.toLowerCase().includes(this.state.search) ||
            adv.partner_id?.[1]?.toLowerCase().includes(this.state.search)
        );
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
        return await this.orm.searchRead(
            "pos.advance.line",
            [["advance_id", "=", advanceId]],
            ["product_id", "qty", "price_unit", "subtotal"]
        );
    }

    // ==================================
    // SELECT ADVANCE
    // ==================================
    async selectAdvance(adv) {
        const customer = adv.partner_id?.[1];
        const lines = await this._loadAdvanceLines(adv.id);

        this.state.selectedAdvance = {
            id: adv.id,
            name: adv.name,
            customer: customer,
            total: adv.total_expected,
            paid: adv.amount_paid,
            remaining: adv.remaining_amount,
            products: lines.map(l => ({
                product_id: l.product_id?.[0],
                product_name: l.product_id?.[1],
                qty: l.qty,
                price_unit: l.price_unit,
                subtotal: l.subtotal,
            })),
        };

        console.log("[ADVANCE] selectedAdvance =", this.state.selectedAdvance);
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

        try {
            await this.orm.call(
                "pos.advance.payment",
                "action_create_invoice",
                [[this.state.selectedAdvance.id], {
                    payment_type: this.state.paymentType,
                }]
            );

            this.notification.add(
                _t("Invoice created successfully."),
                {type: "success"}
            );

            this.props.close();

        } catch (error) {
            console.error(error);
            this.notification.add(
                error.message || _t("Failed to create invoice."),
                {type: "danger"}
            );
        }
    }
}

window.AdvanceOrderListPopup = AdvanceOrderListPopup;
