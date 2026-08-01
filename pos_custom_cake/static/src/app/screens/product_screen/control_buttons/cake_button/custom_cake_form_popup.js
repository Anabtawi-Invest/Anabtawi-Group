/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatCurrency } from "@web/core/currency";
import { rpc } from "@web/core/network/rpc";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";
import { normalize } from "@web/core/l10n/utils";

function roundCurrency(amount, currency) {
    const rounding = currency?.rounding || 0.01;
    return Math.round(amount / rounding) * rounding;
}

export class CustomCakeFormPopup extends Component {
    static template = "pos_custom_cake.CustomCakeFormPopup";
    static components = { Dialog };
    static props = {
        close: Function,
        getPayload: Function,
        pos: Object,
    };

    setup() {
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            loading: true,
            config: null,
            partner: null,
            cake_size_id: 0,
            sugar_paste_choice: "no",
            selectedLines: {},
            categorySearch: {},
            note: "",
        });
        onMounted(async () => {
            await this._loadConfig();
            this.state.loading = false;
        });
    }

    async _loadConfig() {
        try {
            const config = await rpc("/pos/custom_cake/get_config", {
                pos_config_id: this.props.pos.config.id,
            });
            this.state.config = config;
        } catch (error) {
            this.notification.add(error?.message || _t("Failed to load cake configuration."), {
                type: "danger",
            });
        }
    }

    get dialogTitle() {
        return `🎂 ${_t("Custom Cake")}`;
    }

    get labels() {
        return {
            loading: _t("Loading..."),
            customer: _t("Customer"),
            selectCustomer: _t("Select customer..."),
            cakePieces: _t("Cake Pieces"),
            selectSize: _t("Select size..."),
            sugarPaste: _t("Contains Sugar Paste"),
            yes: _t("Yes"),
            no: _t("No"),
            priceSummary: _t("Price Summary"),
            sugarPasteCost: _t("Sugar Paste Cost"),
            totalComponentsCost: _t("Total Components Cost"),
            componentsCost: _t("Components Cost"),
            cakeBase: _t("Cake Base"),
            costAfterOverhead: _t("Cost After Overhead"),
            overhead: _t("Overhead"),
            sellingPriceBeforeTax: _t("Selling Price Before Tax"),
            tax: _t("Tax"),
            finalSellingPrice: _t("Final Selling Price"),
            cancel: _t("Cancel"),
            payLater: _t("Pay Later"),
            confirm: _t("Confirm"),
            searchProduct: _t("Search product..."),
            noProductsFound: _t("No products match your search."),
            note: _t("Note"),
            notePlaceholder: _t("Add special instructions..."),
        };
    }

    formatAmount(amount) {
        return formatCurrency(amount || 0, this.props.pos.currency?.id);
    }

    get categories() {
        return this.state.config?.categories || [];
    }

    get sizes() {
        return this.state.config?.sizes || [];
    }

    get taxRate() {
        return this.state.config?.tax_rate || 16;
    }

    get costDivisor() {
        return this.state.config?.cost_divisor || 0.63;
    }

    get overheadPercent() {
        return this.state.config?.overhead || 0;
    }

    get hasOverhead() {
        return this.overheadPercent > 0;
    }

    _getOverheadDivisor() {
        const overhead = this.overheadPercent;
        if (!overhead) {
            return 1;
        }
        return (100 - overhead) / 100;
    }

    _getSelectedSize() {
        const sizeId = Number(this.state.cake_size_id);
        if (!sizeId) {
            return null;
        }
        return this.sizes.find((s) => Number(s.id) === sizeId) || null;
    }

    _getSelectedPieces() {
        return this._getSelectedSize()?.pieces || 1;
    }

    _getCakeBaseCost() {
        return this._getSelectedSize()?.cake_base_cost || 0;
    }

    get hasCakeBase() {
        return this._getCakeBaseCost() > 0;
    }

    get hasSugarPaste() {
        return this.state.sugar_paste_choice === "yes";
    }

    _getSugarPasteCost(config, pieces) {
        if (!this.hasSugarPaste || !config) {
            return 0;
        }
        const sugarQty = config.sugar_paste_qty || 1;
        return (config.sugar_paste_cost || 0) * sugarQty * pieces;
    }

    /** Recomputed on every render when size, sugar paste, or components change. */
    get priceSummary() {
        const config = this.state.config;
        const empty = {
            components_cost: 0,
            cake_base_cost: 0,
            sugar_paste_cost: 0,
            total_components_cost: 0,
            cost_after_overhead: 0,
            price_before_tax: 0,
            tax_amount: 0,
            final_price: 0,
        };
        if (!config) {
            return empty;
        }

        const pieces = this._getSelectedPieces();
        let componentsCost = 0;
        for (const category of config.categories) {
            const selectedId = this.state.selectedLines[category.id];
            if (!selectedId) {
                continue;
            }
            const line = category.lines.find((l) => l.id === selectedId);
            if (line) {
                componentsCost += (line.cost || 0) * pieces;
            }
        }
        const sugarPasteCost = this._getSugarPasteCost(config, pieces);
        const cakeBaseCost = this._getCakeBaseCost();
        const totalCost = componentsCost + sugarPasteCost + cakeBaseCost;

        const currency = this.props.pos.currency;
        const overheadDivisor = this._getOverheadDivisor();
        const divisor = this.costDivisor || 0.63;
        const taxRate = this.taxRate / 100;
        const costAfterOverhead = roundCurrency(totalCost / overheadDivisor, currency);
        const priceBeforeTax = roundCurrency(costAfterOverhead / divisor, currency);
        const taxAmount = roundCurrency(priceBeforeTax * taxRate, currency);
        const finalPrice = roundCurrency(priceBeforeTax + taxAmount, currency);
        return {
            components_cost: componentsCost,
            cake_base_cost: cakeBaseCost,
            sugar_paste_cost: sugarPasteCost,
            total_components_cost: totalCost,
            cost_after_overhead: costAfterOverhead,
            price_before_tax: priceBeforeTax,
            tax_amount: taxAmount,
            final_price: finalPrice,
        };
    }

    async onSelectPartner() {
        const partner = await makeAwaitable(this.dialog, PartnerList, {
            partner: this.state.partner,
        });
        if (partner) {
            this.state.partner = partner;
        }
    }

    onComponentSelect(categoryId, lineId) {
        this.state.selectedLines = {
            ...this.state.selectedLines,
            [categoryId]: lineId,
        };
    }

    onCategorySearchInput(categoryId, ev) {
        this.state.categorySearch = {
            ...this.state.categorySearch,
            [categoryId]: ev.target.value || "",
        };
    }

    getCategorySearch(categoryId) {
        return this.state.categorySearch[categoryId] || "";
    }

    getFilteredLines(category) {
        const query = normalize((this.state.categorySearch[category.id] || "").trim());
        if (!query) {
            return category.lines;
        }
        const selectedId = this.state.selectedLines[category.id];
        return category.lines.filter(
            (line) =>
                line.id === selectedId ||
                normalize(line.product_name || "").includes(query)
        );
    }

    isComponentSelected(categoryId, lineId) {
        return this.state.selectedLines[categoryId] === lineId;
    }

    getSelectedCount() {
        return Object.keys(this.state.selectedLines).filter(
            (key) => this.state.selectedLines[key]
        ).length;
    }

    _validate() {
        if (!this.state.partner?.id) {
            this.notification.add(_t("Please select a customer."), { type: "warning" });
            return false;
        }
        if (!this.state.cake_size_id) {
            this.notification.add(_t("Please select a cake size."), { type: "warning" });
            return false;
        }
        if (this.getSelectedCount() === 0) {
            this.notification.add(_t("Please select at least one cake component."), {
                type: "warning",
            });
            return false;
        }
        if (this.hasSugarPaste && !this.state.config?.sugar_paste_product_id) {
            this.notification.add(
                _t("Sugar Paste Product is not configured in Custom Cake Settings."),
                { type: "warning" }
            );
            return false;
        }
        return true;
    }

    _buildPayload(payLater) {
        const selectedLines = [];
        for (const category of this.categories) {
            const lineId = this.state.selectedLines[category.id];
            if (lineId) {
                selectedLines.push({ category_line_id: lineId });
            }
        }
        return {
            partner_id: this.state.partner.id,
            cake_size_id: this.state.cake_size_id,
            sugar_paste: this.hasSugarPaste,
            selected_lines: selectedLines,
            pay_later: payLater,
            pos_config_id: this.props.pos.config.id,
            pos_session_id: this.props.pos.session?.id || false,
            note: (this.state.note || "").trim(),
        };
    }

    confirm() {
        if (!this._validate()) {
            return;
        }
        this.props.getPayload({
            action: "confirm",
            payload: this._buildPayload(false),
            prices: { ...this.priceSummary },
            partner: this.state.partner,
        });
        this.props.close();
    }

    payLater() {
        if (!this._validate()) {
            return;
        }
        this.props.getPayload({
            action: "pay_later",
            payload: this._buildPayload(true),
            prices: { ...this.priceSummary },
            partner: this.state.partner,
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
