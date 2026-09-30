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

const CEO_DASHBOARD_STORAGE_KEY = "ceo_main_dashboard_state";

export class CeoMainDashboard extends Component {
    static template = "ceo_main_dashboard.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.limitOptions = [15, 30, 50, 100];
        const today = DateTime.local().toISODate();

        let saved = this.props.action?._dashboardState || null;
        if (!saved) {
            try {
                const raw = sessionStorage.getItem(CEO_DASHBOARD_STORAGE_KEY);
                if (raw) {
                    saved = JSON.parse(raw);
                }
            } catch (e) {
                console.warn("Failed to load CEO dashboard state from sessionStorage", e);
            }
        }

        this._restoringFromSaved = !!saved;

        const preset = (saved && saved.preset) || "today";
        const dateFrom = (saved && saved.dateFrom) || today;
        const dateTo = (saved && saved.dateTo) || today;
        const activeTab = (saved && saved.activeTab) || "purchase";
        const trendFilter = (saved && saved.trendFilter) || "all";
        const limit = (saved && saved.limit) || 100;
        const currentPage = (saved && saved.currentPage) || 1;

        this.state = useState({
            activeTab: activeTab,
            loading: true,
            syncing: false,
            preset: preset,
            dateFrom: dateFrom,
            dateTo: dateTo,
            data: null,
            trendFilter: trendFilter, // 'all' | 'up' | 'down'
            limit: limit,
            currentPage: currentPage,
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

    _saveState() {
        try {
            const stateToSave = {
                preset: this.state.preset,
                dateFrom: this.state.dateFrom,
                dateTo: this.state.dateTo,
                activeTab: this.state.activeTab,
                trendFilter: this.state.trendFilter,
                limit: this.state.limit,
                currentPage: this.state.currentPage,
            };
            if (this.props.action) {
                this.props.action._dashboardState = stateToSave;
            }
            sessionStorage.setItem(CEO_DASHBOARD_STORAGE_KEY, JSON.stringify(stateToSave));
        } catch (e) {
            console.warn("Failed to save CEO dashboard state", e);
        }
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------
    async loadData() {
        this._saveState();
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("ceo.main.dashboard", "get_purchase_dashboard", [
                this.state.dateFrom,
                this.state.dateTo,
            ]);
            this.state.history = {};
            this.state.expandedProductId = null;
            if (!this._restoringFromSaved) {
                this.state.currentPage = 1;
            }
            this._restoringFromSaved = false;
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
        this._saveState();
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
        this._saveState();
        this.loadData();
    }

    onDateChange(field, ev) {
        this.state.preset = "custom";
        this.state[field] = ev.target.value;
        this._saveState();
    }

    applyCustomRange() {
        if (this.state.dateFrom && this.state.dateTo) {
            this._saveState();
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
        this._saveState();
    }

    onLimitChange(ev) {
        this.state.limit = parseInt(ev.target.value, 10) || 100;
        this.state.currentPage = 1;
        this.state.expandedProductId = null;
        this._saveState();
    }

    onSearchInput(ev) {
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
        return rows;
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
            this._saveState();
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
        this._saveState();
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "purchase.order",
            res_id: orderId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openPeriodOrders() {
        const data = this.state.data;
        this._saveState();
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Confirmed Purchase Orders"),
            res_model: "purchase.order",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [
                ["state", "=", "purchase"],
                ["date_approve", ">=", data.utc_from],
                ["date_approve", "<=", data.utc_to],
            ],
        });
    }

    openProduct(productId) {
        this._saveState();
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
