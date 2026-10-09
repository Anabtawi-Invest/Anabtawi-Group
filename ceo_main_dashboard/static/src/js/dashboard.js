/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";

const { DateTime } = luxon;

const CHART_WIDTH = 560;
const CHART_HEIGHT = 150;
const CHART_PADDING = 22;

export class CeoMainDashboard extends Component {
    static template = "ceo_main_dashboard.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.limitOptions = [15, 30, 50, 100];
        const today = DateTime.local().toISODate();

        this.state = useState({
            activeTab: "purchase",
            loading: true,
            syncing: false,
            preset: "today",
            dateFrom: today,
            dateTo: today,
            data: null,
            billing: "all", // 'all' | 'invoiced' | 'not_invoiced'
            trendFilter: "all", // 'all' | 'up' | 'down'
            impactFilter: null, // null | 'extra' | 'saved' | 'net'
            limit: 100,
            currentPage: 1,
            searchTerm: "",
            searchResults: null,
            searching: false,
            expandedProductId: null,
            history: {},
            historyLoading: false,
        });

        this.debouncedSearch = useDebounced(this.runSearch, 400);
        onWillStart(() => this.loadData());
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------
    async loadData() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("ceo.main.dashboard", "get_purchase_dashboard", [
                this.state.dateFrom,
                this.state.dateTo,
                this.state.billing,
            ]);
            this.state.history = {};
            this.state.expandedProductId = null;
            this.state.currentPage = 1;
            if (this.state.searchTerm.trim()) {
                await this.runSearch();
            }
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        this.state.syncing = true;
        try {
            await this.loadData();
            this.notification.add(_t("Dashboard refreshed"), { type: "success" });
        } finally {
            this.state.syncing = false;
        }
    }

    switchTab(tab) {
        this.state.activeTab = tab;
    }

    // ------------------------------------------------------------------
    // Date filters
    // ------------------------------------------------------------------
    setPreset(preset) {
        const now = DateTime.local();
        let from = now;
        let to = now;
        switch (preset) {
            case "today":
                break;
            case "yesterday":
                from = to = now.minus({ days: 1 });
                break;
            case "week":
                from = now.startOf("week");
                break;
            case "month":
                from = now.startOf("month");
                break;
            case "quarter":
                from = now.startOf("quarter");
                break;
            case "year":
                from = now.startOf("year");
                break;
            default:
                return;
        }
        this.state.preset = preset;
        this.state.dateFrom = from.toISODate();
        this.state.dateTo = to.toISODate();
        this.loadData();
    }

    onDateChange(field, ev) {
        this.state.preset = "custom";
        this.state[field] = ev.target.value;
    }

    applyCustomRange() {
        if (this.state.dateFrom && this.state.dateTo) {
            this.loadData();
        }
    }

    setBilling(billing) {
        if (this.state.billing !== billing) {
            this.state.billing = billing;
            this.loadData();
        }
    }

    // ------------------------------------------------------------------
    // Price comparison table: filters, search, history
    // ------------------------------------------------------------------
    setTrendFilter(trend) {
        this.state.trendFilter = trend;
        this.state.currentPage = 1;
        this.state.expandedProductId = null;
    }

    setImpactFilter(filter) {
        this.state.impactFilter = this.state.impactFilter === filter ? null : filter;
        this.state.trendFilter = "all";
        this.state.searchTerm = "";
        this.state.searchResults = null;
        this.state.currentPage = 1;
        this.state.expandedProductId = null;
        if (this.state.impactFilter) {
            const panel = document.querySelector(".cmd_price_panel");
            if (panel) {
                panel.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        }
    }

    impactFilterLabel(filter) {
        return {
            extra: _t("Extra paid (products with a positive period impact)"),
            saved: _t("Saved (products with a negative period impact)"),
            net: _t("Net impact (all products with a period impact)"),
        }[filter];
    }

    onLimitChange(ev) {
        this.state.limit = parseInt(ev.target.value, 10) || 100;
        this.state.currentPage = 1;
        this.state.expandedProductId = null;
    }

    onSearchInput(ev) {
        this.state.impactFilter = null;
        this.state.searchTerm = ev.target.value;
        this.state.currentPage = 1;
        this.state.expandedProductId = null;
        if (!this.state.searchTerm.trim()) {
            this.state.searchResults = null;
            return;
        }
        this.debouncedSearch();
    }

    clearSearch() {
        this.state.searchTerm = "";
        this.state.searchResults = null;
        this.state.currentPage = 1;
        this.state.expandedProductId = null;
    }

    async runSearch() {
        const term = this.state.searchTerm.trim();
        if (!term) {
            this.state.searchResults = null;
            return;
        }
        this.state.searching = true;
        try {
            const rows = await this.orm.call("ceo.main.dashboard", "search_purchase_prices", [
                term,
                this.state.dateTo,
            ]);
            if (term === this.state.searchTerm.trim()) {
                this.state.searchResults = rows;
            }
        } finally {
            this.state.searching = false;
        }
    }

    get isSearchMode() {
        return this.state.searchResults !== null;
    }

    get allRows() {
        if (this.isSearchMode) {
            return this.state.searchResults;
        }
        return (this.state.data && this.state.data.price_rows) || [];
    }

    get filteredRows() {
        let rows = this.allRows;
        if (this.state.trendFilter !== "all") {
            rows = rows.filter((r) => r.trend === this.state.trendFilter);
        }
        const impactFilter = !this.isSearchMode && this.state.impactFilter;
        if (impactFilter === "extra") {
            rows = rows.filter((r) => r.impact > 0).sort((a, b) => b.impact - a.impact);
        } else if (impactFilter === "saved") {
            rows = rows.filter((r) => r.impact < 0).sort((a, b) => a.impact - b.impact);
        } else if (impactFilter === "net") {
            rows = rows.filter((r) => r.impact).sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact));
        }
        return rows;
    }

    get filteredImpactTotal() {
        return this.filteredRows.reduce((total, r) => total + (r.impact || 0), 0);
    }

    get totalPages() {
        return Math.max(1, Math.ceil(this.filteredRows.length / this.state.limit));
    }

    get currentPage() {
        if (this.state.currentPage > this.totalPages) {
            return 1;
        }
        if (this.state.currentPage < 1) {
            return 1;
        }
        return this.state.currentPage;
    }

    get visibleRows() {
        const page = this.currentPage;
        const start = (page - 1) * this.state.limit;
        return this.filteredRows.slice(start, start + this.state.limit);
    }

    get startItem() {
        if (!this.filteredRows.length) {
            return 0;
        }
        return (this.currentPage - 1) * this.state.limit + 1;
    }

    get endItem() {
        return Math.min(this.currentPage * this.state.limit, this.filteredRows.length);
    }

    get pages() {
        const total = this.totalPages;
        const current = this.currentPage;
        if (total <= 9) {
            return Array.from({ length: total }, (_, i) => i + 1);
        }
        let start = Math.max(1, current - 4);
        let end = Math.min(total, current + 4);
        if (current <= 5) {
            start = 1;
            end = 9;
        } else if (current + 4 >= total) {
            start = total - 8;
            end = total;
        }
        const pageList = [];
        for (let p = start; p <= end; p++) {
            pageList.push(p);
        }
        return pageList;
    }

    setPage(page) {
        const target = Math.max(1, Math.min(page, this.totalPages));
        if (this.state.currentPage !== target) {
            this.state.currentPage = target;
            this.state.expandedProductId = null;
            const tableElem = document.querySelector(".cmd_panel .cmd_table_wrap");
            if (tableElem) {
                tableElem.scrollIntoView({ behavior: "smooth", block: "nearest" });
            }
        }
    }

    prevPage() {
        this.setPage(this.currentPage - 1);
    }

    nextPage() {
        this.setPage(this.currentPage + 1);
    }

    firstPage() {
        this.setPage(1);
    }

    lastPage() {
        this.setPage(this.totalPages);
    }

    countTrend(trend) {
        if (!this.isSearchMode && this.state.data) {
            return this.state.data.impact[`${trend}_count`] || 0;
        }
        return this.allRows.filter((r) => r.trend === trend).length;
    }

    async toggleHistory(row) {
        const productId = row.product_id;
        if (this.state.expandedProductId === productId) {
            this.state.expandedProductId = null;
            return;
        }
        this.state.expandedProductId = productId;
        if (!this.state.history[productId]) {
            this.state.historyLoading = true;
            try {
                this.state.history[productId] = await this.orm.call(
                    "ceo.main.dashboard",
                    "get_product_price_history",
                    [productId, this.state.dateTo]
                );
            } finally {
                this.state.historyLoading = false;
            }
        }
    }

    historyChart(productId) {
        const points = this.state.history[productId] || [];
        const chart = { width: CHART_WIDTH, height: CHART_HEIGHT, path: "", dots: [] };
        if (!points.length) {
            return chart;
        }
        const prices = points.map((p) => p.price);
        const min = Math.min(...prices);
        const max = Math.max(...prices);
        const span = max - min;
        const innerW = CHART_WIDTH - 2 * CHART_PADDING;
        const innerH = CHART_HEIGHT - 2 * CHART_PADDING;
        const step = points.length > 1 ? innerW / (points.length - 1) : 0;

        chart.dots = points.map((p, i) => ({
            key: p.line_id,
            x: points.length > 1 ? CHART_PADDING + i * step : CHART_WIDTH / 2,
            y: span ? CHART_PADDING + innerH - ((p.price - min) / span) * innerH : CHART_HEIGHT / 2,
            trend: p.trend,
            title: `${this.fmtDate(p.date)} · ${p.vendor} · ${this.fmtPrice(p.price)}`,
        }));
        chart.path = chart.dots.map((d) => `${d.x.toFixed(1)},${d.y.toFixed(1)}`).join(" ");
        return chart;
    }

    // ------------------------------------------------------------------
    // Drill-down actions
    // ------------------------------------------------------------------
    openOrder(orderId) {
        if (!orderId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.order",
            res_id: orderId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openReceipt(pickingId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "stock.picking",
            res_id: pickingId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openBill(moveId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: moveId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openPeriodReceipts() {
        const data = this.state.data;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Purchase Receipts"),
            res_model: "stock.picking",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [
                ["state", "=", "done"],
                ["move_ids.purchase_line_id", "!=", false],
                ["date_done", ">=", data.utc_from],
                ["date_done", "<=", data.utc_to],
            ],
        });
    }

    async openBills(dateFrom = null, dateTo = null) {
        const action = await this.orm.call("ceo.main.dashboard", "action_open_period_bills", [
            dateFrom,
            dateTo,
        ]);
        this.action.doAction(action);
    }

    openPeriodBills() {
        this.openBills(this.state.data.date_from, this.state.data.date_to);
    }

    openTodayBills() {
        this.openBills();
    }

    openProduct(productId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.product",
            res_id: productId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ------------------------------------------------------------------
    // Display helpers
    // ------------------------------------------------------------------
    trendLabel(trend) {
        return {
            up: _t("Increased"),
            down: _t("Decreased"),
            same: _t("No change"),
            new: _t("First purchase"),
        }[trend];
    }

    billingLabel(status) {
        return {
            invoiced: _t("Invoiced"),
            none: _t("Not invoiced"),
            partial: _t("Partially invoiced"),
        }[status];
    }

    trendIcon(trend) {
        return {
            up: "fa-arrow-up",
            down: "fa-arrow-down",
            same: "fa-minus",
            new: "fa-star-o",
        }[trend];
    }

    changeClass(value) {
        if (value === null || value === undefined || Math.abs(value) < 1e-9) {
            return "";
        }
        return value > 0 ? "cmd_text_up" : "cmd_text_down";
    }

    qtyDiffers(received, ordered) {
        return Math.abs((Number(received) || 0) - (Number(ordered) || 0)) > 1e-6;
    }

    pricesDiffer(a, b) {
        return Math.abs((Number(a) || 0) - (Number(b) || 0)) > 1e-6;
    }

    barHeight(amount) {
        const max = this.state.data.daily.max_amount;
        return max ? Math.max(2, (amount / max) * 100) : 0;
    }

    get currency() {
        return (this.state.data && this.state.data.currency) || { symbol: "", position: "before", decimals: 2 };
    }

    _fmtNumber(amount, decimals) {
        return Math.abs(amount).toLocaleString(undefined, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    }

    _withSymbol(text, negative) {
        const { symbol, position } = this.currency;
        const sign = negative ? "-" : "";
        return position === "after" ? `${sign}${text} ${symbol}` : `${sign}${symbol} ${text}`;
    }

    fmtMoney(amount) {
        amount = Number(amount) || 0;
        return this._withSymbol(this._fmtNumber(amount, this.currency.decimals), amount < 0);
    }

    fmtPrice(amount) {
        if (amount === null || amount === undefined) {
            return "—";
        }
        amount = Number(amount) || 0;
        return this._withSymbol(this._fmtNumber(amount, Math.max(this.currency.decimals, 2)), amount < 0);
    }

    fmtSignedPrice(amount) {
        amount = Number(amount) || 0;
        if (Math.abs(amount) < 1e-9) {
            return this.fmtPrice(0);
        }
        return (amount > 0 ? "+" : "") + this.fmtPrice(amount);
    }

    fmtSignedMoney(amount) {
        amount = Number(amount) || 0;
        if (Math.abs(amount) < 1e-9) {
            return this.fmtMoney(0);
        }
        return (amount > 0 ? "+" : "") + this.fmtMoney(amount);
    }

    fmtPct(value) {
        if (value === null || value === undefined || isNaN(value)) {
            return "—";
        }
        const sign = value > 0 ? "+" : "";
        return `${sign}${Number(value).toFixed(1)}%`;
    }

    fmtQty(value) {
        return (Number(value) || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });
    }

    fmtDate(isoDate) {
        return isoDate ? DateTime.fromISO(isoDate).toFormat("dd LLL yyyy") : "";
    }

    fmtDateTime(value) {
        return value ? DateTime.fromSQL(value).toFormat("dd LLL yyyy HH:mm") : "";
    }

    fmtBarLabel(isoDate) {
        const format = this.state.data.daily.granularity === "month" ? "LLL yy" : "dd LLL";
        return DateTime.fromISO(isoDate).toFormat(format);
    }
}

registry.category("actions").add("ceo_main_dashboard.dashboard", CeoMainDashboard);
