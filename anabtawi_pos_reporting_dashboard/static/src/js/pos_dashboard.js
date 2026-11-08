/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { useSetupAction } from "@web/search/action_hook";

export class PosReportingDashboard extends Component {
    static template = "anabtawi_pos_reporting_dashboard.PosReportingDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        const params = this.props.action?.params || {};
        const today = this._formatLocalDate(new Date());

        const initFrom = (params.date_from || today).slice(0, 10);
        const initTo = (params.date_to || today).slice(0, 10);
        const initConfigs = params.config_ids || [];

        this.state = useState({
            period: "today",
            date_from: initFrom,
            date_to: initTo,
            config_ids: initConfigs,
            loading: true,
            canSeeProducts: false,
            canSeeTransfers: false,
            view: "branches",
            productLoading: false,
            productFilter: "all",
            productSearch: "",
            productSortKey: "qty",
            productSortOrder: "desc",
            categorySearch: "",
            categorySortKey: "category_profit",
            categorySortOrder: "desc",
            transferLoading: false,
            transferFilter: "all",
            transferSearch: "",
            transferSortKey: "where",
            transferSortOrder: "asc",
            compareLoading: false,
            compare_date_from_a: "",
            compare_date_to_a: "",
            compare_date_from_b: "",
            compare_date_to_b: "",
            compare_product_id: false,
            compare_product_label: "",
            compare_product_term: "",
            compareProductOptions: [],
            compareSearch: "",
            compareSortKey: "sales_delta",
            compareSortOrder: "asc",
            sortKey: "sales",
            sortOrder: "desc",
        });
        const monthRanges = this._defaultCompareRanges();
        this.state.compare_date_from_a = monthRanges.aFrom;
        this.state.compare_date_to_a = monthRanges.aTo;
        this.state.compare_date_from_b = monthRanges.bFrom;
        this.state.compare_date_to_b = monthRanges.bTo;

        // Filters restored when coming back through the breadcrumbs.
        const saved = (this.props.state && this.props.state.dashboard) || null;
        if (saved) {
            Object.assign(this.state, saved.filters);
        }

        useSetupAction({
            getLocalState: () => ({
                dashboard: {
                    filters: {
                        period: this.state.period,
                        date_from: this.state.date_from,
                        date_to: this.state.date_to,
                        config_ids: [...(this.state.config_ids || [])],
                        view: this.state.view,
                        productFilter: this.state.productFilter,
                        productSearch: this.state.productSearch,
                        productSortKey: this.state.productSortKey,
                        productSortOrder: this.state.productSortOrder,
                        categorySearch: this.state.categorySearch,
                        categorySortKey: this.state.categorySortKey,
                        categorySortOrder: this.state.categorySortOrder,
                        transferFilter: this.state.transferFilter,
                        transferSearch: this.state.transferSearch,
                        transferSortKey: this.state.transferSortKey,
                        transferSortOrder: this.state.transferSortOrder,
                        compare_date_from_a: this.state.compare_date_from_a,
                        compare_date_to_a: this.state.compare_date_to_a,
                        compare_date_from_b: this.state.compare_date_from_b,
                        compare_date_to_b: this.state.compare_date_to_b,
                        compare_product_id: this.state.compare_product_id,
                        compare_product_label: this.state.compare_product_label,
                        compareSearch: this.state.compareSearch,
                        compareSortKey: this.state.compareSortKey,
                        compareSortOrder: this.state.compareSortOrder,
                        sortKey: this.state.sortKey,
                        sortOrder: this.state.sortOrder,
                    },
                },
            }),
        });

        this.products = useState({
            loadedKey: "",
            summary: {},
            cards: { stock_more: [], best_profit: [], review_price: [], kill: [] },
            category_cards: { best_categories: [], best_available: [], best_unavailable: [], worst_in_stock: [] },
            categories: [],
            products: [],
            error: "",
        });

        this.transfers = useState({
            loadedKey: "",
            summary: {},
            rows: [],
            error: "",
        });

        this.compare = useState({
            loadedKey: "",
            summary: {},
            rows: [],
            date_from_a: "",
            date_to_a: "",
            date_from_b: "",
            date_to_b: "",
            error: "",
        });

        this.data = useState({
            date_from: "",
            date_to: "",
            active_branches_count: 0,
            all_branches: [],
            kpis: {},
            branches: [],
            global_totals: {},
            channels: [],
            trends: [],
        });

        onWillStart(async () => {
            this.state.canSeeProducts = await user.hasGroup(
                "anabtawi_pos_reporting_dashboard.group_pos_dashboard_products"
            );
            this.state.canSeeTransfers = await user.hasGroup(
                "anabtawi_pos_reporting_dashboard.group_pos_dashboard_transfers"
            );
            if (!this.state.canSeeProducts && (this.state.view === "products" || this.state.view === "category_profit" || this.state.view === "compare")) {
                this.state.view = "branches";
            }
            if (!this.state.canSeeTransfers && this.state.view === "transfers") {
                this.state.view = "branches";
            }
            await this.fetchDashboardData();
        });
    }

    _formatLocalDate(dateObj) {
        if (!dateObj) return "";
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, "0");
        const day = String(dateObj.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    _defaultCompareRanges() {
        const now = new Date();
        const aFrom = new Date(now.getFullYear(), now.getMonth(), 1);
        const aTo = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const bFrom = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        const bTo = new Date(now.getFullYear(), now.getMonth(), 0);
        return {
            aFrom: this._formatLocalDate(aFrom),
            aTo: this._formatLocalDate(aTo),
            bFrom: this._formatLocalDate(bFrom),
            bTo: this._formatLocalDate(bTo),
        };
    }

    _filterKey() {
        const configs = this.state.config_ids || [];
        return `${this.state.date_from}|${this.state.date_to}|${configs.join(",")}`;
    }

    _compareFilterKey() {
        const configs = this.state.config_ids || [];
        return [
            this.state.compare_date_from_a,
            this.state.compare_date_to_a,
            this.state.compare_date_from_b,
            this.state.compare_date_to_b,
            this.state.compare_product_id || "",
            configs.join(","),
        ].join("|");
    }

    async fetchDashboardData() {
        if (this.state.view === "products" || this.state.view === "category_profit") {
            await this.fetchProductData();
            return;
        }
        if (this.state.view === "transfers") {
            await this.fetchTransferData();
            return;
        }
        if (this.state.view === "compare") {
            await this.fetchCompareData();
            return;
        }
        this.products.loadedKey = "";
        this.transfers.loadedKey = "";
        this.compare.loadedKey = "";
        this.state.loading = true;        try {
            const strFrom = this.state.date_from;
            const strTo = this.state.date_to;

            const res = await this.orm.call(
                "pos.reporting.dashboard",
                "get_dashboard_data",
                [],
                {
                    date_from: strFrom,
                    date_to: strTo,
                    config_ids: this.state.config_ids,
                }
            );

            this.data.date_from = res.date_from || strFrom;
            this.data.date_to = res.date_to || strTo;
            this.data.kpis = res.kpis || {};
            this.data.branches = res.branches || [];
            this.data.all_branches = res.all_branches || [];
            this.data.global_totals = res.global_totals || {};
            this.data.channels = res.channels || [];
            this.data.trends = res.trends || [];
        } catch (error) {
            console.error("Failed to load POS dashboard data", error);
        } finally {
            this.state.loading = false;
        }
    }

    get sortedBranches() {
        const branches = [...(this.data.branches || [])];
        const key = this.state.sortKey;
        const isAsc = this.state.sortOrder === "asc";

        if (!key) return branches;

        branches.sort((a, b) => {
            let valA = a[key];
            let valB = b[key];

            if (typeof valA === "string") {
                valA = (valA || "").toLowerCase();
                valB = (valB || "").toLowerCase();
                return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }

            valA = Number(valA) || 0;
            valB = Number(valB) || 0;
            return isAsc ? valA - valB : valB - valA;
        });

        return branches;
    }

    sortBy(key) {
        if (this.state.sortKey === key) {
            this.state.sortOrder = this.state.sortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.sortKey = key;
            this.state.sortOrder = key === "branch_name" ? "asc" : "desc";
        }
    }

    setView(view) {
        if (this.state.view === view) {
            return;
        }
        if ((view === "products" || view === "category_profit" || view === "compare") && !this.state.canSeeProducts) {
            return;
        }
        if (view === "transfers" && !this.state.canSeeTransfers) {
            return;
        }
        this.state.view = view;
        if ((view === "products" || view === "category_profit") && this.products.loadedKey !== this._filterKey()) {
            this.fetchProductData();
        } else if (view === "transfers" && this.transfers.loadedKey !== this._filterKey()) {
            this.fetchTransferData();
        } else if (view === "compare" && this.compare.loadedKey !== this._compareFilterKey()) {
            this.fetchCompareData();
        } else if (view === "branches" && !(this.data.branches || []).length) {
            this.fetchDashboardData();
        }
    }

    setComparePreset(which, preset) {
        const now = new Date();
        let fromDate;
        let toDate;
        if (preset === "this_month") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
            toDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        } else if (preset === "prev_month") {
            fromDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
            toDate = new Date(now.getFullYear(), now.getMonth(), 0);
        } else if (preset === "this_week") {
            const day = now.getDay();
            const diff = now.getDate() - day + (day === 0 ? -6 : 1);
            fromDate = new Date(now.getFullYear(), now.getMonth(), diff);
            toDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        } else {
            fromDate = now;
            toDate = now;
        }
        if (which === "a") {
            this.state.compare_date_from_a = this._formatLocalDate(fromDate);
            this.state.compare_date_to_a = this._formatLocalDate(toDate);
        } else {
            this.state.compare_date_from_b = this._formatLocalDate(fromDate);
            this.state.compare_date_to_b = this._formatLocalDate(toDate);
        }
    }

    async onCompareProductTerm(ev) {
        this.state.compare_product_term = ev.target.value || "";
        const term = this.state.compare_product_term.trim();
        if (!term) {
            this.state.compareProductOptions = [];
            return;
        }
        try {
            const options = await this.orm.call(
                "pos.reporting.dashboard",
                "search_compare_products",
                [],
                { term, limit: 20 }
            );
            this.state.compareProductOptions = options || [];
        } catch (error) {
            console.error("Failed to search compare products", error);
            this.state.compareProductOptions = [];
        }
    }

    selectCompareProduct(product) {
        this.state.compare_product_id = product.id;
        this.state.compare_product_label = product.name;
        this.state.compare_product_term = product.name;
        this.state.compareProductOptions = [];
    }

    clearCompareProduct() {
        this.state.compare_product_id = false;
        this.state.compare_product_label = "";
        this.state.compare_product_term = "";
        this.state.compareProductOptions = [];
    }

    onCompareSearch(ev) {
        this.state.compareSearch = ev.target.value || "";
    }

    async fetchCompareData() {
        this.state.compareLoading = true;
        this.state.loading = false;
        this.compare.error = "";
        try {
            const res = await this.orm.call(
                "pos.reporting.dashboard",
                "get_compare_dashboard_data",
                [],
                {
                    date_from_a: this.state.compare_date_from_a,
                    date_to_a: this.state.compare_date_to_a,
                    date_from_b: this.state.compare_date_from_b,
                    date_to_b: this.state.compare_date_to_b,
                    config_ids: this.state.config_ids || [],
                    product_id: this.state.compare_product_id || false,
                }
            );
            this.compare.summary = res.summary || {};
            this.compare.rows = res.rows || [];
            this.compare.date_from_a = res.date_from_a || this.state.compare_date_from_a;
            this.compare.date_to_a = res.date_to_a || this.state.compare_date_to_a;
            this.compare.date_from_b = res.date_from_b || this.state.compare_date_from_b;
            this.compare.date_to_b = res.date_to_b || this.state.compare_date_to_b;
            this.compare.error = res.error || "";
            this.compare.loadedKey = this._compareFilterKey();
            if (res.all_branches && res.all_branches.length) {
                this.data.all_branches = res.all_branches;
            }
        } catch (error) {
            console.error("Failed to load compare dashboard", error);
            this.compare.error = "The comparison did not load.";
        } finally {
            this.state.compareLoading = false;
        }
    }

    get sortedCompareRows() {
        const query = (this.state.compareSearch || "").trim().toLowerCase();
        let rows = [...(this.compare.rows || [])];
        if (query) {
            rows = rows.filter((row) =>
                (row.product_name || "").toLowerCase().includes(query)
                || (row.branch_name || "").toLowerCase().includes(query)
            );
        }
        const key = this.state.compareSortKey;
        const isAsc = this.state.compareSortOrder === "asc";
        rows.sort((a, b) => {
            let valA = a[key];
            let valB = b[key];
            if (typeof valA === "string" || typeof valB === "string") {
                valA = (valA || "").toLowerCase();
                valB = (valB || "").toLowerCase();
                return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }
            valA = Number(valA) || 0;
            valB = Number(valB) || 0;
            return isAsc ? valA - valB : valB - valA;
        });
        return rows;
    }

    sortCompare(key) {
        if (this.state.compareSortKey === key) {
            this.state.compareSortOrder = this.state.compareSortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.compareSortKey = key;
            this.state.compareSortOrder = (
                key === "product_name" || key === "branch_name" ? "asc" : "asc"
            );
        }
    }

    compareDirectionClass(direction) {
        if (direction === "up") return "text-success fw-semibold";
        if (direction === "down") return "text-danger fw-semibold";
        return "text-muted";
    }

    compareDirectionIcon(direction) {
        if (direction === "up") return "▲";
        if (direction === "down") return "▼";
        return "●";
    }

    compareSummaryDelta() {
        return this.compare.summary?.sales_delta || { amount: 0, percent: 0, direction: "flat" };
    }

    compareSummaryBadgeClass() {
        const direction = this.compareSummaryDelta().direction;
        if (direction === "up") return "bg-success";
        if (direction === "down") return "bg-danger";
        return "bg-secondary";
    }

    async exportCompareExcel() {
        try {
            const action = await this.orm.call(
                "pos.reporting.dashboard",
                "action_export_compare_xlsx",
                [],
                {
                    date_from_a: this.state.compare_date_from_a,
                    date_to_a: this.state.compare_date_to_a,
                    date_from_b: this.state.compare_date_from_b,
                    date_to_b: this.state.compare_date_to_b,
                    config_ids: this.state.config_ids || [],
                    product_id: this.state.compare_product_id || false,
                    sort_key: this.state.compareSortKey || "sales_delta",
                    sort_order: this.state.compareSortOrder || "asc",
                    search: this.state.compareSearch || "",
                }
            );
            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to export compare Excel", error);
        }
    }

    setTransferFilter(filter) {
        this.state.transferFilter = filter;
    }

    onTransferSearch(ev) {
        this.state.transferSearch = ev.target.value || "";
    }

    async fetchTransferData() {
        this.state.transferLoading = true;
        this.state.loading = false;
        this.transfers.error = "";
        try {
            const res = await this.orm.call(
                "pos.reporting.dashboard",
                "get_transfer_dashboard_data",
                [],
                {
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    config_ids: this.state.config_ids || [],
                }
            );
            this.transfers.summary = res.summary || {};
            this.transfers.rows = res.rows || [];
            this.transfers.error = res.error || "";
            this.transfers.loadedKey = this._filterKey();
            if (res.all_branches && res.all_branches.length) {
                this.data.all_branches = res.all_branches;
            }
            this.data.date_from = res.date_from || this.state.date_from;
            this.data.date_to = res.date_to || this.state.date_to;
        } catch (error) {
            console.error("Failed to load transfer dashboard", error);
            this.transfers.error = "The transfer list did not load.";
        } finally {
            this.state.transferLoading = false;
        }
    }

    get sortedTransfers() {
        const query = (this.state.transferSearch || "").trim().toLowerCase();
        const filter = this.state.transferFilter;
        let rows = [...(this.transfers.rows || [])];
        if (filter === "mismatch") {
            rows = rows.filter((row) => row.where !== "ok");
        } else if (filter === "not_approved") {
            rows = rows.filter((row) => row.not_approved);
        } else if (filter === "send") {
            rows = rows.filter((row) => Math.abs(row.send_gap || 0) > 0.0005);
        } else if (filter === "receive") {
            rows = rows.filter((row) => !row.not_approved && Math.abs(row.receive_gap || 0) > 0.0005);
        }
        if (query) {
            rows = rows.filter((row) =>
                (row.product_name || "").toLowerCase().includes(query)
                || (row.branch_name || "").toLowerCase().includes(query)
                || (row.request_picking_name || "").toLowerCase().includes(query)
                || (row.receipt_picking_name || "").toLowerCase().includes(query)
                || (row.where_label || "").toLowerCase().includes(query)
            );
        }
        const key = this.state.transferSortKey;
        const isAsc = this.state.transferSortOrder === "asc";
        const whereRank = {
            waiting: 0,
            send_waiting: 1,
            both: 2,
            send: 3,
            receive: 4,
            mixed: 5,
            ok: 6,
        };
        rows.sort((a, b) => {
            let valA = a[key];
            let valB = b[key];
            if (key === "where") {
                valA = whereRank[a.where] ?? 9;
                valB = whereRank[b.where] ?? 9;
            }
            if (typeof valA === "string" || typeof valB === "string") {
                valA = (valA || "").toLowerCase();
                valB = (valB || "").toLowerCase();
                return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }
            const missingA = valA === null || valA === undefined;
            const missingB = valB === null || valB === undefined;
            if (missingA || missingB) {
                if (missingA && missingB) return 0;
                return missingA ? 1 : -1;
            }
            return isAsc ? valA - valB : valB - valA;
        });
        return rows;
    }

    sortTransfers(key) {
        if (this.state.transferSortKey === key) {
            this.state.transferSortOrder = this.state.transferSortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.transferSortKey = key;
            this.state.transferSortOrder = (
                key === "branch_name"
                || key === "product_name"
                || key === "where"
                || key === "request_picking_name"
                || key === "receipt_picking_name"
            ) ? "asc" : "desc";
        }
    }

    async openTransferPicking(pickingId) {
        if (!pickingId) {
            return;
        }
        try {
            const action = await this.orm.call(
                "pos.reporting.dashboard",
                "open_transfer_picking",
                [],
                { picking_id: pickingId }
            );
            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to open transfer", error);
        }
    }

    transferWhereClass(where) {
        if (where === "ok") return "text-success";
        if (where === "waiting" || where === "send_waiting") return "text-warning";
        if (where === "send" || where === "receive" || where === "both" || where === "mixed") return "text-danger";
        return "";
    }

    hasTransferGap(value) {
        return Math.abs(Number(value) || 0) > 0.0005;
    }

    setProductFilter(filter) {
        this.state.productFilter = filter;
    }

    showAllProducts() {
        this.state.productFilter = "all";
        this.state.productSearch = "";
    }

    onProductSearch(ev) {
        this.state.productSearch = ev.target.value || "";
    }

    async fetchProductData() {
        this.state.productLoading = true;
        this.products.error = "";
        try {
            const res = await this.orm.call(
                "pos.reporting.dashboard",
                "get_product_dashboard_data",
                [],
                {
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    config_ids: this.state.config_ids || [],
                }
            );
            this.products.summary = res.summary || {};
            this.products.cards = res.cards || { stock_more: [], best_profit: [], review_price: [], kill: [] };
            this.products.category_cards = res.category_cards || { best_categories: [], best_available: [], best_unavailable: [], worst_in_stock: [] };
            this.products.categories = res.categories || [];
            this.products.products = res.products || [];
            this.products.loadedKey = this._filterKey();
        } catch (error) {
            console.error("Failed to load POS product dashboard", error);
            this.products.error = "The product list did not load.";
        } finally {
            this.state.productLoading = false;
        }
    }

    get sortedProducts() {
        const query = (this.state.productSearch || "").trim().toLowerCase();
        const filter = this.state.productFilter;
        let rows = [...(this.products.products || [])];
        if (filter === "unsold") {
            rows = rows.filter((row) => row.decision === "kill");
        } else if (filter && filter !== "all") {
            rows = rows.filter((row) => row.decision === filter);
        }
        if (query) {
            rows = rows.filter((row) =>
                (row.name || "").toLowerCase().includes(query)
                || (row.branch_name || "").toLowerCase().includes(query)
                || (row.category || "").toLowerCase().includes(query)
            );
        }
        const key = this.state.productSortKey;
        const isAsc = this.state.productSortOrder === "asc";
        rows.sort((a, b) => {
            let valA = a[key];
            let valB = b[key];
            if (typeof valA === "string" || typeof valB === "string") {
                valA = (valA || "").toLowerCase();
                valB = (valB || "").toLowerCase();
                return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }
            const missingA = valA === null || valA === undefined;
            const missingB = valB === null || valB === undefined;
            if (missingA || missingB) {
                if (missingA && missingB) return 0;
                return missingA ? 1 : -1;
            }
            return isAsc ? valA - valB : valB - valA;
        });
        return rows;
    }

    sortProducts(key) {
        if (this.state.productSortKey === key) {
            this.state.productSortOrder = this.state.productSortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.productSortKey = key;
            this.state.productSortOrder = key === "name" || key === "branch_name" || key === "category" || key === "decision_label" ? "asc" : "desc";
        }
    }

    onCategorySearch(ev) {
        this.state.categorySearch = ev.target.value || "";
    }

    get sortedCategoryRows() {
        const query = (this.state.categorySearch || "").trim().toLowerCase();
        let rows = [...(this.products.products || [])];
        if (query) {
            rows = rows.filter((row) =>
                (row.name || "").toLowerCase().includes(query)
                || (row.branch_name || "").toLowerCase().includes(query)
                || (row.category || "").toLowerCase().includes(query)
            );
        }
        const key = this.state.categorySortKey;
        const isAsc = this.state.categorySortOrder === "asc";
        rows.sort((a, b) => {
            let valA = a[key];
            let valB = b[key];
            if (typeof valA === "string" || typeof valB === "string") {
                valA = (valA || "").toLowerCase();
                valB = (valB || "").toLowerCase();
                return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }
            const missingA = valA === null || valA === undefined;
            const missingB = valB === null || valB === undefined;
            if (missingA || missingB) {
                if (missingA && missingB) return 0;
                return missingA ? 1 : -1;
            }
            return isAsc ? valA - valB : valB - valA;
        });
        return rows;
    }

    sortCategoryRows(key) {
        if (this.state.categorySortKey === key) {
            this.state.categorySortOrder = this.state.categorySortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.categorySortKey = key;
            this.state.categorySortOrder = key === "name" || key === "branch_name" || key === "category" ? "asc" : "desc";
        }
    }

    formatMargin(value) {
        if (value === undefined || value === null || value === "") {
            return "—";
        }
        return `${Number(value).toLocaleString("en-US", {
            minimumFractionDigits: 1,
            maximumFractionDigits: 1,
        })}%`;
    }

    async openProductLines(productId, configId) {
        try {
            const action = await this.orm.call(
                "pos.reporting.dashboard",
                "open_product_lines",
                [],
                {
                    product_id: productId,
                    config_id: configId || false,
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    config_ids: this.state.config_ids || [],
                }
            );
            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to open product lines", error);
        }
    }

    selectBranch(branchId) {
        if (branchId === "all") {
            this.state.config_ids = [];
        } else {
            this.state.config_ids = [branchId];
        }
        this.fetchDashboardData();
    }

    isBranchSelected(branchId) {
        if (branchId === "all") {
            return !this.state.config_ids || this.state.config_ids.length === 0;
        }
        return this.state.config_ids && this.state.config_ids.length === 1 && this.state.config_ids[0] === branchId;
    }

    setPeriod(period) {
        this.state.period = period;
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        let fromDate = today;
        let toDate = today;

        if (period === "yesterday") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
            toDate = fromDate;
        } else if (period === "this_week") {
            const day = now.getDay();
            const diff = now.getDate() - day + (day === 0 ? -6 : 1);
            fromDate = new Date(now.getFullYear(), now.getMonth(), diff);
        } else if (period === "this_month") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
        }

        this.state.date_from = this._formatLocalDate(fromDate);
        this.state.date_to = this._formatLocalDate(toDate);
        this.fetchDashboardData();
    }

    formatCurrency(amount) {
        if (amount === undefined || amount === null) return "0.000";
        return Number(amount).toLocaleString("en-US", {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3,
        });
    }

    formatDecimal(amount, decimals = 2) {
        if (amount === undefined || amount === null) return "0.00";
        return Number(amount).toLocaleString("en-US", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    }

    getPercent(value, total) {
        if (!total || total === 0) return "0.0";
        return ((value / total) * 100).toFixed(1);
    }

    async onKpiClick(metricType, configId = null) {
        try {
            const strFrom = this.state.date_from;
            const strTo = this.state.date_to;
            const targetConfigs = configId ? [configId] : (this.state.config_ids || []);

            const action = await this.orm.call(
                "pos.reporting.dashboard",
                "open_kpi_drilldown",
                [],
                {
                    metric_type: metricType,
                    date_from: strFrom,
                    date_to: strTo,
                    config_ids: targetConfigs,
                }
            );

            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to open KPI drilldown action", error);
        }
    }

    async exportExcel() {
        try {
            const strFrom = this.state.date_from;
            const strTo = this.state.date_to;

            const wizardVals = {
                date_from: strFrom,
                date_to: strTo,
            };
            if (this.state.config_ids && this.state.config_ids.length > 0) {
                wizardVals.config_ids = [[6, 0, this.state.config_ids]];
            }

            const wizard = await this.orm.create("pos.unified.report.wizard", [wizardVals]);

            const action = await this.orm.call(
                "pos.unified.report.wizard",
                "action_export_xlsx",
                [wizard[0]]
            );

            this.actionService.doAction(action);
        } catch (error) {
            console.error("Failed to export Excel report", error);
        }
    }

    async exportProductsExcel() {
        try {
            const action = await this.orm.call(
                "pos.reporting.dashboard",
                "action_export_products_xlsx",
                [],
                {
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    config_ids: this.state.config_ids || [],
                    product_filter: this.state.productFilter || "all",
                    product_search: this.state.productSearch || "",
                    sort_key: this.state.productSortKey || "qty",
                    sort_order: this.state.productSortOrder || "desc",
                }
            );
            if (action) {
                this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to export POS menu Excel", error);
        }
    }
}

registry.category("actions").add("pos_reporting_dashboard_main", PosReportingDashboard);
