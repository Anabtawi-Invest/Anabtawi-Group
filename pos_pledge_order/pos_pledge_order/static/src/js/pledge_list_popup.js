/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { formatCurrency } from "@web/core/currency";
import { getAdvanceEligiblePaymentMethods } from "@pos_advance_order/app/screens/product_screen/control_buttons/advance_order_button/advance_order_form_popup";

export class PledgeListPopup extends Component {
    static template = "pos_pledge.PledgeListPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        partnerId: { type: Number, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.pos = usePos();
        const paymentMethods = getAdvanceEligiblePaymentMethods(this.pos);
        const defaultPmId = paymentMethods.length ? paymentMethods[0].id : null;

        this.state = useState({
            pledges: [],
            selectedPledgeIds: [],
            search: "",
            selectedPledgeDetails: null,
            payment_methods: paymentMethods,
            selected_payment_method_id: defaultPmId,
        });

        onMounted(() => this._loadPledges());
    }

    get title() {
        return _t("Select Pledge(s) to Return");
    }

    get selectedCountLabel() {
        return _t("%s pledge(s) selected", this.state.selectedPledgeIds.length);
    }

    get detailsTitle() {
        return _t("Pledge Details");
    }

    get searchPlaceholder() {
        return _t("Search by pledge number, customer name, phone, or employee name...");
    }

    get noActivePledgesLabel() {
        return _t("No active pledges found.");
    }

    get noSearchResultsLabel() {
        return _t("No pledges match your search.");
    }

    get showLabel() {
        return _t("Show");
    }

    get unselectLabel() {
        return _t("Unselect");
    }

    get cancelLabel() {
        return _t("Cancel");
    }

    get closeLabel() {
        return _t("Close");
    }

    get returnPledgeLabel() {
        return _t("Return Pledge");
    }

    get paymentMethodLabel() {
        return _t("Return payment method");
    }

    get returnHintText() {
        return _t(
            "The pledge amount will be returned to the customer from the selected payment method."
        );
    }

    get noEligiblePaymentMethodsText() {
        return _t(
            "No eligible payment methods on this POS. Add manual cash or bank methods without terminal or QR integration in the Point of Sale configuration."
        );
    }

    get customerLabel() {
        return _t("Customer:");
    }

    get employeeLabel() {
        return _t("Employee:");
    }

    get amountsLabel() {
        return _t("Amounts");
    }

    get pledgeAmountLabel() {
        return _t("Pledge Amount:");
    }

    get employeeServiceLabel() {
        return _t("Employee Service:");
    }

    get deliveryServiceLabel() {
        return _t("Delivery Service:");
    }

    get productsLabel() {
        return _t("Products");
    }

    get productColumnLabel() {
        return _t("Product");
    }

    get qtyColumnLabel() {
        return _t("Qty");
    }

    get caseTypeLabel() {
        return _t("Case Type:");
    }

    get createdLabel() {
        return _t("Created:");
    }

    get returnedLabel() {
        return _t("Returned:");
    }

    get activePledgesFoundLabel() {
        return _t("%s active pledge(s) found", this.state.pledges.length);
    }

    get showingPledgesLabel() {
        return _t("Showing %s of %s pledges", this.filteredPledges.length, this.state.pledges.length);
    }

    get selectedPledges() {
        const selected = new Set(this.state.selectedPledgeIds);
        return this.state.pledges.filter((p) => selected.has(p.id));
    }

    get hasSelectedPledges() {
        return this.state.selectedPledgeIds.length > 0;
    }

    get selectedReturnTotal() {
        return this.selectedPledges.reduce(
            (sum, pledge) => sum + Number(pledge.pledge_amount ?? 0),
            0
        );
    }

    get selectedReturnAmountFmt() {
        const currencyId = this.pos?.currency?.id;
        return formatCurrency(this.selectedReturnTotal, currencyId);
    }

    isPledgeSelected(pledge) {
        return this.state.selectedPledgeIds.includes(pledge.id);
    }

    paymentMethodIconSrc(pm) {
        if (!pm) {
            return "";
        }
        if (pm.image) {
            return `/web/image/pos.payment.method/${pm.id}/image`;
        }
        if (pm.type === "cash") {
            return "/point_of_sale/static/src/img/money.png";
        }
        return "/point_of_sale/static/src/img/card-bank.png";
    }

    isPaymentSelected(pm) {
        return pm.id === this.state.selected_payment_method_id;
    }

    paymentMethodRowClass(pm) {
        const selected = this.isPaymentSelected(pm);
        return `button paymentmethod btn btn-secondary btn-lg lh-lg d-flex justify-content-between align-items-center flex-fill text-start ${selected ? "border border-3 border-primary" : "opacity-75"}`;
    }

    pledgeCardClass(pledge) {
        const selected = this.isPledgeSelected(pledge);
        return selected ? "card mb-2 border border-3 border-primary" : "card mb-2";
    }

    togglePledgeSelection(pledge) {
        const ids = [...this.state.selectedPledgeIds];
        const index = ids.indexOf(pledge.id);
        if (index >= 0) {
            ids.splice(index, 1);
        } else {
            ids.push(pledge.id);
        }
        this.state.selectedPledgeIds = ids;
    }

    selectPaymentMethod(pm) {
        this.state.selected_payment_method_id = pm.id;
    }

    // ==================================
    // LOAD ACTIVE PLEDGES (FILTERED BY RETURN TYPE)
    // ==================================
    async _loadPledges() {
        try {
            const domain = [["state", "=", "active"]];
            if (this.props.partnerId) {
                domain.push(["partner_id", "=", this.props.partnerId]);
            }

            const rows = await this.orm.searchRead(
                "pos.advance.order.pledge",
                domain,
                [
                    "id",
                    "order_id",
                    "pos_order_id",
                    "partner_id",
                    "employee_id",
                    "product_id",
                    "pledge_qty",
                    "pledge_amount_unit",
                    "pledge_subtotal",
                    "create_date",
                    "state",
                    "return_date",
                ],
                { order: "create_date desc" }
            );
            this.state.pledges = rows.map((row) => ({
                ...row,
                name: row.order_id?.[1] || row.pos_order_id?.[1] || _t("POS Pledge"),
                pledge_amount: row.pledge_subtotal || 0,
                employee_amount: 0,
                delivery_amount: 0,
                case_type: "case2",
            }));

            const employeeIds = this.state.pledges
                .map((p) => p.employee_id && p.employee_id[0])
                .filter((id) => id);

            if (employeeIds.length > 0) {
                const employees = await this.orm.searchRead(
                    "hr.employee",
                    [["id", "in", employeeIds]],
                    ["id", "name"],
                    {}
                );

                const employeeMap = {};
                employees.forEach((emp) => {
                    employeeMap[emp.id] = emp.name;
                });

                this.state.pledges = this.state.pledges.map((pledge) => {
                    if (pledge.employee_id && pledge.employee_id[0]) {
                        pledge.employee_name = employeeMap[pledge.employee_id[0]] || "";
                    } else {
                        pledge.employee_name = "";
                    }
                    return pledge;
                });
            }

            const partnerIds = [...new Set(this.state.pledges.map((p) => p.partner_id?.[0]).filter(Boolean))];
            if (partnerIds.length > 0) {
                const partners = await this.orm.searchRead(
                    "res.partner",
                    [["id", "in", partnerIds]],
                    ["id", "phone"]
                );

                const partnerPhoneMap = {};
                partners.forEach((partner) => {
                    partnerPhoneMap[partner.id] = partner.phone || "";
                });

                this.state.pledges = this.state.pledges.map((pledge) => {
                    if (pledge.partner_id && pledge.partner_id[0]) {
                        pledge.partner_phone = partnerPhoneMap[pledge.partner_id[0]] || "";
                    } else {
                        pledge.partner_phone = "";
                    }
                    return pledge;
                });
            }
            console.log("[PLEDGE] Loaded", this.state.pledges.length, "active pledges");
        } catch (error) {
            console.error("[PLEDGE] Error loading pledges:", error);
            this.notification.add(_t("Failed to load pledges"), { type: "danger" });
        }
    }

    onSearchInput(ev) {
        this.state.search = (ev.target.value || "").toLowerCase();
    }

    get filteredPledges() {
        if (!this.state.search) {
            return this.state.pledges;
        }

        const searchLower = this.state.search.toLowerCase();
        return this.state.pledges.filter(
            (pledge) =>
                pledge.name?.toLowerCase().includes(searchLower) ||
                pledge.partner_id?.[1]?.toLowerCase().includes(searchLower) ||
                pledge.employee_name?.toLowerCase().includes(searchLower) ||
                (pledge.partner_phone && pledge.partner_phone.toString().toLowerCase().includes(searchLower))
        );
    }

    onSearchKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }

        ev.preventDefault();

        if (!this.filteredPledges.length) {
            this.notification.add(_t("No pledge found."), { type: "warning" });
            return;
        }

        this.highlightPledge(this.filteredPledges[0]);
    }

    highlightPledge(pledge) {
        this.togglePledgeSelection(pledge);
    }

    confirmReturn() {
        if (!this.hasSelectedPledges) {
            this.notification.add(_t("Please select at least one pledge to return."), { type: "warning" });
            return;
        }
        if (!this.state.selected_payment_method_id) {
            this.notification.add(_t("Please select a payment method."), { type: "warning" });
            return;
        }
        const selectedPm = this.state.payment_methods.find(
            (pm) => pm.id === this.state.selected_payment_method_id
        );
        this.props.getPayload({
            pledge_ids: [...this.state.selectedPledgeIds],
            pledges: this.selectedPledges,
            payment_method_id: this.state.selected_payment_method_id,
            payment_method_name: selectedPm?.name || "",
            total_amount: this.selectedReturnTotal,
        });
        this.props.close();
    }

    cancel() {
        this.props.getPayload(null);
        this.props.close();
    }

    async showPledgeDetails(pledge) {
        try {
            const pledgeDetails = await this.orm.searchRead(
                "pos.advance.order.pledge",
                [["id", "=", pledge.id]],
                [
                    "id",
                    "order_id",
                    "pos_order_id",
                    "partner_id",
                    "employee_id",
                    "product_id",
                    "pledge_qty",
                    "pledge_amount_unit",
                    "pledge_subtotal",
                    "create_date",
                    "return_date",
                    "state",
                ],
                { limit: 1 }
            );

            if (!pledgeDetails || !pledgeDetails.length) {
                this.notification.add(_t("Failed to load pledge details"), { type: "warning" });
                return;
            }

            const fullPledge = pledgeDetails[0];
            const products = fullPledge.product_id
                ? [
                      {
                          id: fullPledge.product_id[0],
                          name: fullPledge.product_id[1],
                          qty: fullPledge.pledge_qty || 1,
                      },
                  ]
                : [];

            this.state.selectedPledgeDetails = {
                ...fullPledge,
                name: fullPledge.order_id?.[1] || fullPledge.pos_order_id?.[1] || _t("POS Pledge"),
                pledge_amount: fullPledge.pledge_subtotal || 0,
                employee_amount: 0,
                delivery_amount: 0,
                case_type: "case2",
                employee_name: pledge.employee_name || "",
                partner_phone: pledge.partner_phone || "",
                products,
            };
        } catch (error) {
            console.error("[PLEDGE] Error loading pledge details:", error);
            this.notification.add(
                _t("Failed to load pledge details: %s", error.message || error),
                { type: "danger" }
            );
        }
    }

    formatCurrency(amount) {
        return this.pos.env.utils.formatCurrency(amount, false);
    }
}
