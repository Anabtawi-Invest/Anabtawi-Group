/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const STORAGE_KEY = "executive_company_cost_dashboard_state";
const FOCUS_CODES = ["RENT", "PAYROLL", "UTILITIES", "TECH", "DELIVERY", "SECURITY", "LOSS"];
const BUCKET_ICONS = {
    REV_RETAIL: "fa-shopping-basket",
    REV_LOCAL: "fa-handshake-o",
    REV_EXPORT: "fa-globe",
    REV_ADJ: "fa-tags",
    REVENUE: "fa-money",
    OTHER_INCOME: "fa-plus-circle",
    COGS: "fa-cubes",
    FACTORY_OH: "fa-industry",
    PAYROLL: "fa-users",
    RENT: "fa-building",
    UTILITIES: "fa-bolt",
    TECH: "fa-wifi",
    DELIVERY: "fa-motorcycle",
    FLEET: "fa-truck",
    SECURITY: "fa-shield",
    MAINTENANCE: "fa-wrench",
    LOSS: "fa-trash",
    MARKETING: "fa-bullhorn",
    GOVT: "fa-gavel",
    FINANCE: "fa-university",
    DEPRECIATION: "fa-line-chart",
    OTHER_OPEX: "fa-ellipsis-h",
};
const BENCHMARK_CODES = ["COGS", "PAYROLL", "RENT", "UTILITIES", "TECH", "DELIVERY", "FLEET", "LOSS"];

// Chart geometry
const TREND = { w: 760, h: 250, l: 54, r: 12, t: 14, b: 28 };
const WATERFALL = { w: 560, h: 250, l: 10, r: 10, t: 22, b: 46 };

function niceStep(range, ticks) {
    const raw = range / ticks || 1;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    return (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
}

function niceScale(min, max, ticks = 4) {
    if (max === min) {
        max = min + 1;
    }
    const step = niceStep(max - min, ticks);
    return { min: Math.floor(min / step) * step, max: Math.ceil(max / step) * step, step };
}

function compact(v) {
    const a = Math.abs(v);
    const sign = v < 0 ? "-" : "";
    if (a >= 1e9) return `${sign}${(a / 1e9).toFixed(1)}B`;
    if (a >= 1e6) return `${sign}${(a / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`;
    if (a >= 1e3) return `${sign}${(a / 1e3).toFixed(a >= 1e4 ? 0 : 1)}K`;
    return `${sign}${Math.round(a)}`;
}

export class ExecutiveCostDashboard extends Component {
    static template = "executive_company_cost_dashboard.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        let saved = {};
        try {
            saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "{}") || {};
        } catch {
            saved = {};
        }
        this.state = useState({
            loading: true,
            busy: false,
            error: "",
            data: null,
            tab: saved.tab || "overview",
            periodMode: saved.periodMode || "ytd",
            year: saved.year || new Date().getFullYear(),
            dateFrom: saved.dateFrom || "",
            dateTo: saved.dateTo || "",
            companyId: saved.companyId || 0,
            hoverMonth: null,
            explorerId: saved.explorerId || 0,
            explorerSearch: "",
            explorerKind: saved.explorerKind || "all",
            finderQuery: saved.finderQuery || "",
            finderSelected: null,
            finderGroup: "",
        });
        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    get filters() {
        return {
            period_mode: this.state.periodMode,
            year: this.state.year,
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            company_id: this.state.companyId || 0,
        };
    }

    saveState() {
        try {
            const { tab, periodMode, year, dateFrom, dateTo, companyId, explorerId, explorerKind, finderQuery } = this.state;
            sessionStorage.setItem(
                STORAGE_KEY,
                JSON.stringify({ tab, periodMode, year, dateFrom, dateTo, companyId, explorerId, explorerKind, finderQuery })
            );
        } catch {
            /* storage may be unavailable */
        }
    }

    async load() {
        this.saveState();
        const first = !this.state.data;
        this.state.loading = first;
        this.state.busy = !first;
        this.state.error = "";
        try {
            const data = await this.orm.call("ceo.cost.dashboard.report", "get_executive_dashboard_data", [this.filters]);
            this.state.data = data;
            if (this.state.periodMode === "custom" && !this.state.dateFrom) {
                this.state.dateFrom = data.period.date_from;
                this.state.dateTo = data.period.date_to;
            }
        } catch (error) {
            this.state.error = (error && error.data && error.data.message) || (error && error.message) || String(error);
        } finally {
            this.state.loading = false;
            this.state.busy = false;
        }
    }

    async refresh() {
        await this.load();
        if (!this.state.error) {
            this.notification.add(_t("Dashboard refreshed"), { type: "success" });
        }
    }

    // ------------------------------------------------------------------
    // Filters / navigation
    // ------------------------------------------------------------------
    get periods() {
        return [
            { key: "this_month", label: _t("This Month") },
            { key: "last_month", label: _t("Last Month") },
            { key: "qtd", label: _t("This Quarter") },
            { key: "ytd", label: _t("Year to Date") },
            { key: "last_12m", label: _t("Last 12 Months") },
            { key: "year", label: _t("Full Year") },
            { key: "custom", label: _t("Custom") },
        ];
    }

    get tabs() {
        return [
            { key: "overview", label: _t("Overview"), icon: "fa-tachometer" },
            { key: "companies", label: _t("Companies"), icon: "fa-industry" },
            { key: "explorer", label: _t("Branches & Departments"), icon: "fa-sitemap" },
            { key: "finder", label: _t("Expenses"), icon: "fa-search" },
        ];
    }

    setTab(tab, bucket) {
        if (tab === "costs") {
            // a cost group: open the expense list filtered on that group
            tab = "finder";
            this.state.finderGroup = bucket || "";
            this.state.finderQuery = "";
            this.state.finderSelected = null;
        } else if (tab === "branches" || tab === "departments") {
            tab = "explorer";
            this.state.explorerKind = tab === "branches" ? "branch" : "department";
        }
        this.state.tab = tab;
        this.saveState();
    }

    async setPeriod(mode) {
        this.state.periodMode = mode;
        if (mode === "custom" && !this.state.dateFrom && this.state.data) {
            this.state.dateFrom = this.state.data.period.date_from;
            this.state.dateTo = this.state.data.period.date_to;
        }
        if (mode !== "custom") {
            await this.load();
        }
    }

    async onYear(ev) {
        this.state.year = parseInt(ev.target.value, 10);
        this.state.periodMode = "year";
        await this.load();
    }

    async onCompany(ev) {
        this.state.companyId = parseInt(ev.target.value, 10) || 0;
        await this.load();
    }

    async onDate(field, ev) {
        this.state[field] = ev.target.value;
        if (this.state.dateFrom && this.state.dateTo) {
            this.state.periodMode = "custom";
            await this.load();
        }
    }

    // ------------------------------------------------------------------
    // Formatting
    // ------------------------------------------------------------------
    get decimals() {
        return (this.state.data && this.state.data.currency.decimals) || 0;
    }

    money(value, forceDecimals) {
        const v = Number(value || 0);
        const dec = forceDecimals !== undefined ? forceDecimals : Math.abs(v) >= 100 ? 0 : this.decimals;
        return new Intl.NumberFormat("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(v);
    }

    compact(value) {
        return compact(Number(value || 0));
    }

    pct(value, digits = 1) {
        if (value === null || value === undefined) {
            return "–";
        }
        return `${Number(value).toFixed(digits)}%`;
    }

    signedPct(value) {
        if (value === null || value === undefined) {
            return "–";
        }
        const v = Number(value);
        return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
    }

    /** CSS tone of a change: good / bad / flat, depending on whether growth is desirable. */
    tone(delta, higherIsBetter = true) {
        if (delta === null || delta === undefined || Math.abs(delta) < 0.05) {
            return "flat";
        }
        return delta > 0 === higherIsBetter ? "good" : "bad";
    }

    arrow(delta) {
        if (delta === null || delta === undefined || Math.abs(delta) < 0.05) {
            return "fa-minus";
        }
        return delta > 0 ? "fa-caret-up" : "fa-caret-down";
    }

    monthLabel(key, withYear = false) {
        const [y, m] = key.split("-").map(Number);
        const label = new Date(y, m - 1, 1).toLocaleString("en-US", { month: "short" });
        return withYear ? `${label} ${String(y).slice(2)}` : label;
    }

    dateLabel(iso) {
        if (!iso) {
            return "";
        }
        const [y, m, d] = iso.split("-").map(Number);
        return new Date(y, m - 1, d).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
    }

    get periodLabel() {
        const p = this.state.data && this.state.data.period;
        return p ? `${this.dateLabel(p.date_from)} – ${this.dateLabel(p.date_to)}` : "";
    }

    get prevLabel() {
        const p = this.state.data && this.state.data.period;
        return p ? `${this.dateLabel(p.prev_from)} – ${this.dateLabel(p.prev_to)}` : "";
    }

    get companyLabel() {
        const d = this.state.data;
        if (!d) {
            return "";
        }
        if (d.filters.company_id) {
            const c = d.companies_available.find((x) => x.id === d.filters.company_id);
            return c ? c.name : "";
        }
        return d.companies_available.length > 1 ? _t("All companies (consolidated)") : (d.companies_available[0] || {}).name || "";
    }

    get updatedAt() {
        const d = this.state.data;
        if (!d) {
            return "";
        }
        const dt = new Date(d.meta.generated_at.replace(" ", "T") + "Z");
        return dt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    }

    get hasData() {
        const s = this.state.data && this.state.data.summary;
        return !!s && (s.revenue !== 0 || s.total_cost !== 0 || s.other_income !== 0);
    }

    statusLabel(status) {
        return {
            healthy: _t("Healthy"),
            watch: _t("Watch"),
            loss: _t("Loss"),
            salesonly: _t("Sales only"),
            nodata: _t("No data"),
        }[status];
    }

    icon(code) {
        return BUCKET_ICONS[code] || "fa-circle";
    }

    // ------------------------------------------------------------------
    // KPI cards
    // ------------------------------------------------------------------
    get kpis() {
        const d = this.state.data;
        if (!d) {
            return [];
        }
        const s = d.summary;
        const p = d.prev_summary;
        const series = (key) => d.monthly.map((m) => m[key]);
        const ppDelta = (cur, prev) => (prev ? Math.round((cur - prev) * 100) / 100 : null);
        return [
            {
                key: "revenue",
                label: _t("Revenue"),
                icon: "fa-line-chart",
                value: s.revenue,
                prev: p.revenue,
                delta: this.rel(s.revenue, p.revenue),
                higher: true,
                sub: _t("Gross margin %s", this.pct(s.gross_margin)),
                spark: series("revenue"),
                color: "#0f9d75",
            },
            {
                key: "gross",
                label: _t("Gross Profit"),
                icon: "fa-balance-scale",
                value: s.gross_profit,
                prev: p.gross_profit,
                delta: this.rel(s.gross_profit, p.gross_profit),
                higher: true,
                sub: _t("%s of revenue", this.pct(s.gross_margin)),
                spark: series("gross_profit"),
                color: "#2f80ed",
            },
            {
                key: "cost",
                label: _t("Total Costs"),
                icon: "fa-credit-card",
                value: s.total_cost,
                prev: p.total_cost,
                delta: this.rel(s.total_cost, p.total_cost),
                higher: false,
                sub: _t("%s of revenue", this.pct(s.cost_ratio)),
                spark: series("cost"),
                color: "#d9822b",
            },
            {
                key: "operating",
                label: _t("Operating Profit"),
                icon: "fa-cogs",
                value: s.operating_profit,
                prev: p.operating_profit,
                delta: this.rel(s.operating_profit, p.operating_profit),
                higher: true,
                sub: _t("%s operating margin", this.pct(s.operating_margin)),
                spark: null,
                color: "#7c5cff",
            },
            {
                key: "net",
                label: _t("Net Profit"),
                icon: "fa-trophy",
                value: s.net_profit,
                prev: p.net_profit,
                delta: this.rel(s.net_profit, p.net_profit),
                higher: true,
                sub: _t("%s net margin", this.pct(s.net_margin)),
                spark: series("net_profit"),
                color: s.net_profit >= 0 ? "#0b1f3a" : "#d64545",
                hero: true,
            },
            {
                key: "ratio",
                label: _t("Cost per 1 of Sales"),
                icon: "fa-percent",
                value: s.cost_ratio / 100,
                isRatio: true,
                prev: p.cost_ratio / 100,
                delta: ppDelta(s.cost_ratio, p.cost_ratio),
                deltaIsPoints: true,
                higher: false,
                sub: _t("Operating result per 1.00 of sales: %s", this.money((s.operating_profit / (s.revenue || 1)), 3)),
                spark: null,
                color: "#c9a24b",
            },
        ];
    }

    rel(cur, prev) {
        if (!prev) {
            return null;
        }
        return Math.round(((cur - prev) / Math.abs(prev)) * 10000) / 100;
    }

    // ------------------------------------------------------------------
    // Charts (inline SVG: no external library, works in RTL and print)
    // ------------------------------------------------------------------
    sparkPaths(values, w = 96, h = 30) {
        if (!values || values.length < 2) {
            return null;
        }
        const min = Math.min(...values, 0);
        const max = Math.max(...values, 0);
        const range = max - min || 1;
        const x = (i) => (i / (values.length - 1)) * (w - 2) + 1;
        const y = (v) => h - 2 - ((v - min) / range) * (h - 4);
        const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
        return {
            line: `M${pts.join("L")}`,
            area: `M${x(0).toFixed(1)},${y(0).toFixed(1)}L${pts.join("L")}L${x(values.length - 1).toFixed(1)},${y(0).toFixed(1)}Z`,
            last: { x: x(values.length - 1), y: y(values[values.length - 1]) },
            w,
            h,
        };
    }

    get trendChart() {
        const d = this.state.data;
        if (!d || !d.monthly.length) {
            return null;
        }
        const { w, h, l, r, t, b } = TREND;
        const rows = d.monthly;
        const max = Math.max(...rows.map((m) => Math.max(m.revenue, m.cost, m.net_profit)), 0);
        const min = Math.min(...rows.map((m) => m.net_profit), 0);
        const scale = niceScale(min, max || 1, 4);
        const innerW = w - l - r;
        const innerH = h - t - b;
        const y = (v) => t + innerH - ((v - scale.min) / (scale.max - scale.min)) * innerH;
        const slot = innerW / rows.length;
        const bw = Math.min(22, slot * 0.3);
        const zero = y(0);
        const grid = [];
        for (let v = scale.min; v <= scale.max + 1e-9; v += scale.step) {
            grid.push({ y: y(v), label: compact(v), zero: Math.abs(v) < 1e-9 });
        }
        const bars = [];
        const linePts = [];
        const labels = [];
        rows.forEach((m, i) => {
            const cx = l + slot * i + slot / 2;
            const rv = y(m.revenue);
            const cv = y(m.cost);
            bars.push(
                { key: `r${i}`, cls: "rev", x: cx - bw - 1, y: Math.min(rv, zero), w: bw, h: Math.abs(zero - rv), idx: i },
                { key: `c${i}`, cls: "cost", x: cx + 1, y: Math.min(cv, zero), w: bw, h: Math.abs(zero - cv), idx: i }
            );
            linePts.push({ x: cx, y: y(m.net_profit), neg: m.net_profit < 0, idx: i, key: `n${i}` });
            labels.push({ x: cx, text: this.monthLabel(m.month, i === 0 || m.month.endsWith("-01")), key: `l${i}` });
        });
        return {
            w,
            h,
            l,
            r: w - r,
            grid,
            bars,
            labels,
            labelY: h - 8,
            dots: linePts,
            line: linePts.length > 1 ? `M${linePts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join("L")}` : "",
            slot,
            t,
            innerH,
        };
    }

    get hoveredMonth() {
        const d = this.state.data;
        return d && this.state.hoverMonth !== null ? d.monthly[this.state.hoverMonth] : null;
    }

    setHover(idx) {
        this.state.hoverMonth = idx;
    }

    get waterfall() {
        const d = this.state.data;
        if (!d) {
            return null;
        }
        const s = d.summary;
        const { w, h, l, r, t, b } = WATERFALL;
        const steps = [
            { label: _t("Revenue"), kind: "total", value: s.revenue, cls: "rev" },
            { label: _t("Cost of Revenue"), kind: "delta", value: -s.cogs, cls: "cost" },
            { label: _t("Gross Profit"), kind: "total", value: s.gross_profit, cls: "gross" },
            { label: _t("Operating Exp."), kind: "delta", value: -s.opex, cls: "cost" },
            { label: _t("Operating Profit"), kind: "total", value: s.operating_profit, cls: "gross" },
            { label: _t("Other Income"), kind: "delta", value: s.other_income, cls: "rev" },
            { label: _t("Net Profit"), kind: "total", value: s.net_profit, cls: s.net_profit >= 0 ? "net" : "neg" },
        ];
        let running = 0;
        steps.forEach((st) => {
            if (st.kind === "total") {
                st.from = 0;
                st.to = st.value;
                running = st.value;
            } else {
                st.from = running;
                st.to = running + st.value;
                running = st.to;
            }
        });
        const all = steps.flatMap((st) => [st.from, st.to, 0]);
        const scale = niceScale(Math.min(...all), Math.max(...all, 1), 4);
        const innerW = w - l - r;
        const innerH = h - t - b;
        const y = (v) => t + innerH - ((v - scale.min) / (scale.max - scale.min)) * innerH;
        const slot = innerW / steps.length;
        const bw = slot * 0.62;
        return {
            w,
            h,
            zero: y(0),
            l,
            r: w - r,
            bars: steps.map((st, i) => {
                const top = y(Math.max(st.from, st.to));
                const bottom = y(Math.min(st.from, st.to));
                return {
                    key: `w${i}`,
                    cls: st.cls,
                    label: st.label,
                    value: st.value,
                    x: l + slot * i + (slot - bw) / 2,
                    y: top,
                    w: bw,
                    h: Math.max(bottom - top, 1.5),
                    cx: l + slot * i + slot / 2,
                    labelY: h - b + 16,
                    valueY: top - 6,
                    connector: i < steps.length - 1 ? y(st.to) : null,
                    nextX: l + slot * (i + 1) + (slot - bw) / 2,
                    x2: l + slot * i + (slot - bw) / 2 + bw,
                };
            }),
        };
    }

    /** Where each unit of revenue goes: cost buckets then profit. */
    get allocation() {
        const d = this.state.data;
        if (!d || !d.summary.revenue) {
            return null;
        }
        const revenue = d.summary.revenue;
        const costs = d.buckets.filter((b) => b.family === "cost" && b.amount > 0).sort((a, b) => b.amount - a.amount);
        const totalCost = costs.reduce((acc, b) => acc + b.amount, 0);
        const base = Math.max(revenue, totalCost);
        const segs = costs.map((b) => ({
            key: b.code,
            code: b.code,
            name: b.name,
            color: b.color,
            amount: b.amount,
            pct: (b.amount / base) * 100,
            ofRevenue: b.pct_revenue,
        }));
        const profit = revenue - totalCost;
        if (profit > 0) {
            segs.push({
                key: "__profit",
                name: _t("Operating profit"),
                color: "#0f9d75",
                amount: profit,
                pct: (profit / base) * 100,
                ofRevenue: (profit / revenue) * 100,
                profit: true,
            });
        }
        return { segs, loss: profit < 0 ? -profit : 0 };
    }

    get donut() {
        const d = this.state.data;
        if (!d) {
            return null;
        }
        const costs = d.buckets.filter((b) => b.family === "cost" && b.amount > 0).sort((a, b) => b.amount - a.amount);
        const total = costs.reduce((acc, b) => acc + b.amount, 0);
        if (!total) {
            return null;
        }
        const top = costs.slice(0, 8);
        const rest = costs.slice(8).reduce((acc, b) => acc + b.amount, 0);
        const items = top.map((b) => ({ key: b.code, code: b.code, name: b.name, color: b.color, amount: b.amount }));
        if (rest > 0) {
            items.push({ key: "__rest", name: _t("Other buckets"), color: "#cbd5e1", amount: rest });
        }
        let offset = 0;
        items.forEach((it) => {
            it.pct = (it.amount / total) * 100;
            it.dash = `${Math.max(it.pct - 0.4, 0.1)} ${100 - Math.max(it.pct - 0.4, 0.1)}`;
            it.offset = -offset;
            offset += it.pct;
        });
        return { items, total };
    }

    // ------------------------------------------------------------------
    // Overview helpers
    // ------------------------------------------------------------------
    get focusCards() {
        const d = this.state.data;
        if (!d) {
            return [];
        }
        const d_th = d.thresholds;
        return FOCUS_CODES.map((code) => d.buckets.find((b) => b.code === code))
            .filter(Boolean)
            .map((b) => {
                let tone = "ok";
                if (b.code === "RENT") {
                    tone = b.pct_revenue >= d_th.rent_danger_pct ? "bad" : b.pct_revenue >= d_th.rent_warn_pct ? "warn" : "ok";
                } else if (b.code === "DELIVERY") {
                    tone = b.pct_revenue >= d_th.delivery_warn_pct ? "warn" : "ok";
                } else if (b.code === "LOSS") {
                    tone = b.pct_revenue >= d_th.loss_warn_pct ? "warn" : "ok";
                }
                return { ...b, tone };
            });
    }

    get topBranches() {
        return this.rankedBranches.slice(0, 5);
    }

    get bottomBranches() {
        const rows = this.rankedBranches;
        return rows.length > 5 ? rows.slice(-5).reverse() : [];
    }

    get rankedBranches() {
        const d = this.state.data;
        if (!d) {
            return [];
        }
        return d.branches.rows.filter((r) => r.status !== "nodata").sort((a, b) => b.net_profit - a.net_profit);
    }

    get revenueStreams() {
        const d = this.state.data;
        return d ? d.buckets.filter((b) => b.family === "income" && b.kind === "revenue") : [];
    }

    goBucket(segment) {
        if (!segment.profit && segment.code) {
            this.setTab("costs", segment.code);
        }
    }

    bucketMeta(code) {
        const d = this.state.data;
        return (d && d.buckets.find((b) => b.code === code)) || { name: code, color: "#94a3b8" };
    }

    // ------------------------------------------------------------------
    // Companies
    // ------------------------------------------------------------------
    get companyRows() {
        return this.state.data ? this.state.data.companies : [];
    }

    get benchmark() {
        const d = this.state.data;
        if (!d) {
            return { cols: [], rows: [] };
        }
        const cols = BENCHMARK_CODES.map((code) => ({ code, ...this.bucketMeta(code) })).filter((c) =>
            d.companies.some((co) => (co.buckets[c.code] || 0) > 0)
        );
        const rows = d.companies.map((co) => ({
            id: co.id,
            name: co.name,
            revenue: co.revenue,
            gross_margin: co.gross_margin,
            net_margin: co.net_margin,
            cells: cols.map((c) => (co.revenue > 0 ? ((co.buckets[c.code] || 0) / co.revenue) * 100 : null)),
        }));
        const active = rows.filter((r) => r.revenue > 0);
        cols.forEach((c, i) => {
            const vals = active.map((r) => r.cells[i]).filter((v) => v !== null && v > 0);
            c.best = vals.length > 1 ? Math.min(...vals) : null;
            c.worst = vals.length > 1 ? Math.max(...vals) : null;
        });
        return { cols, rows };
    }

    cellTone(col, value) {
        if (value === null || value === undefined || col.best === null) {
            return "";
        }
        if (value === col.best) {
            return "good";
        }
        return value === col.worst ? "bad" : "";
    }

    // ------------------------------------------------------------------
    // Branches
    // ------------------------------------------------------------------
    // ------------------------------------------------------------------
    // Cost breakdown matrix (HR / utilities / rent per branch & department)
    // ------------------------------------------------------------------
    get entityKinds() {
        return [
            { key: "all", label: _t("Everything") },
            { key: "branch", label: _t("Branches") },
            { key: "department", label: _t("Departments") },
            { key: "factory", label: _t("Factory") },
        ];
    }

    kindLabel(kind) {
        return { branch: _t("Branch"), department: _t("Dept."), factory: _t("Factory") }[kind] || kind;
    }

    // ------------------------------------------------------------------
    // Explorer: pick any branch / department and see every cost
    // ------------------------------------------------------------------
    get explorerList() {
        const d = this.state.data;
        if (!d) {
            return [];
        }
        const q = this.state.explorerSearch.trim().toLowerCase();
        const kind = this.state.explorerKind;
        return d.entities.filter(
            (e) =>
                (kind === "all" || e.kind === kind) &&
                (!q || e.name.toLowerCase().includes(q) || (e.full_name || "").toLowerCase().includes(q))
        );
    }

    get selectedEntity() {
        const d = this.state.data;
        if (!d || !d.entities.length) {
            return null;
        }
        return (
            d.entities.find((e) => e.id === this.state.explorerId) ||
            d.entities.find((e) => e.cost > 0) ||
            d.entities[0]
        );
    }

    get entityView() {
        const d = this.state.data;
        const e = this.selectedEntity;
        if (!d || !e) {
            return null;
        }
        const names = (topic) => Object.fromEntries(((d.matrix[topic] || {}).columns || []).map((c) => [c.key, c.name]));
        const detail = (topic) => {
            const labels = names(topic);
            const subs = e.subs[topic] || {};
            const total = Object.values(subs).reduce((a, b) => a + b, 0);
            return Object.entries(subs)
                .map(([key, amount]) => ({ key, name: labels[key] || key, amount, pct: total ? (amount / total) * 100 : 0 }))
                .sort((a, b) => b.amount - a.amount);
        };
        const cards = [
            { code: "PAYROLL", label: _t("People cost (HR)"), icon: "fa-users" },
            { code: "UTILITIES", label: _t("Utilities"), icon: "fa-bolt" },
            { code: "RENT", label: _t("Rent & occupancy"), icon: "fa-building" },
        ].map((c) => {
            const amount = e.buckets[c.code] || 0;
            const prev = e.prev_buckets[c.code] || 0;
            return {
                ...c,
                amount,
                delta: this.rel(amount, prev),
                pct: e.cost ? (amount / e.cost) * 100 : 0,
                color: this.bucketMeta(c.code).color,
            };
        });
        const buckets = Object.entries(e.buckets)
            .map(([code, amount]) => {
                const prev = e.prev_buckets[code] || 0;
                return {
                    ...this.bucketMeta(code),
                    code,
                    amount,
                    prev,
                    delta: this.rel(amount, prev),
                    pct: e.cost ? (amount / e.cost) * 100 : 0,
                };
            })
            .sort((a, b) => b.amount - a.amount);
        return {
            e,
            cards,
            buckets,
            hr: detail("hr"),
            utilities: detail("utilities"),
            rent: detail("rent"),
            bars: this.miniBars(e.trend.map((t) => t.cost), e.trend.map((t) => t.month), "#d9822b"),
        };
    }

    selectEntity(id) {
        this.state.explorerId = id;
        this.saveState();
    }

    openEntity(id) {
        this.state.explorerId = id;
        this.setTab("explorer");
    }

    drillEntity(e) {
        this.openJournalItems([...this.baseDomain(), ["analytic_distribution", "in", [e.id]]], e.full_name || e.name);
    }

    exportEntity() {
        const v = this.entityView;
        const rows = v.buckets.map((b) => [b.name, b.amount, b.prev, b.delta, b.pct]);
        this.downloadCsv("cost_detail_" + v.e.name + ".csv", ["Cost", "Amount", "Previous period", "Change %", "% of total cost"], rows);
    }

    /** Small bar chart (inline SVG) for a monthly series. */
    miniBars(values, months, color) {
        if (!values || !values.length) {
            return null;
        }
        const w = 560;
        const h = 120;
        const pad = { l: 8, r: 8, t: 14, b: 20 };
        const max = Math.max(...values, 1);
        const slot = (w - pad.l - pad.r) / values.length;
        const bw = Math.min(26, slot * 0.6);
        return {
            w,
            h,
            color,
            base: h - pad.b,
            bars: values.map((v, i) => {
                const bh = (v / max) * (h - pad.t - pad.b);
                return {
                    key: "mb" + i,
                    x: pad.l + slot * i + (slot - bw) / 2,
                    y: h - pad.b - bh,
                    w: bw,
                    h: Math.max(bh, v ? 1.5 : 0),
                    cx: pad.l + slot * i + slot / 2,
                    label: this.monthLabel(months[i]),
                    value: v,
                    tip: this.monthLabel(months[i], true) + ": " + this.money(v),
                };
            }),
        };
    }

    // ------------------------------------------------------------------
    // Expense finder: every expense with its total, click one for the breakdown
    // ------------------------------------------------------------------
    get finderChips() {
        return [
            { q: "internet", label: _t("Internet") },
            { q: "software", label: _t("Software / Odoo") },
            { q: "electricity", label: _t("Electricity") },
            { q: "water", label: _t("Water") },
            { q: "rent", label: _t("Rent") },
            { q: "salary", label: _t("Salaries") },
            { q: "social security", label: _t("Social security") },
            { q: "health", label: _t("Health insurance") },
            { q: "phone", label: _t("Phones") },
            { q: "fuel", label: _t("Fuel") },
            { q: "security", label: _t("Security") },
            { q: "delivery", label: _t("Delivery commissions") },
        ];
    }

    get finderMatches() {
        const d = this.state.data;
        if (!d) {
            return [];
        }
        const tokens = this.state.finderQuery.trim().toLowerCase().split(/\s+/).filter(Boolean);
        const group = this.state.finderGroup;
        return d.expenses.filter((a) => (!group || a.bucket === group) && tokens.every((t) => a.search.includes(t)));
    }

    get finderGroups() {
        const d = this.state.data;
        return d ? d.buckets.filter((b) => b.family === "cost").sort((a, b) => b.amount - a.amount) : [];
    }

    onFinderGroup(ev) {
        this.state.finderGroup = ev.target.value;
        this.state.finderSelected = null;
    }

    get explorerTotal() {
        return this.explorerList.reduce((acc, e) => acc + e.cost, 0);
    }

    get finderView() {
        const d = this.state.data;
        const matches = this.finderMatches;
        if (!d) {
            return null;
        }
        const picked = matches.find((a) => a.id === this.state.finderSelected);
        const items = picked ? [picked] : matches;
        const months = d.monthly.map((m) => m.month);
        const sum = (key) => items.reduce((acc, a) => acc + a[key], 0);
        const merge = (key, field) => {
            const map = new Map();
            items.forEach((a) =>
                a[key].forEach((x) => {
                    const cur = map.get(x.id) || { ...x, amount: 0 };
                    cur.amount += x.amount;
                    map.set(x.id, cur);
                })
            );
            return [...map.values()].sort((a, b) => b.amount - a.amount);
        };
        const amount = sum("amount");
        const prev = sum("prev");
        const trend = months.map((m, i) => items.reduce((acc, a) => acc + (a.trend[i] || 0), 0));
        const unallocated = sum("unallocated");
        const entities = merge("entities");
        const companies = merge("companies");
        return {
            picked,
            count: items.length,
            total: matches.reduce((acc, a) => acc + a.amount, 0),
            title: picked
                ? picked.name
                : this.state.finderGroup
                  ? this.bucketMeta(this.state.finderGroup).name
                  : this.state.finderQuery.trim()
                    ? _t("All matching expenses")
                    : _t("All expenses"),
            subtitle: picked ? picked.code + " · " + picked.bucket_name : _t("%s accounts", items.length),
            amount,
            prev,
            delta: this.rel(amount, prev),
            pctRevenue: d.summary.revenue ? (amount / d.summary.revenue) * 100 : 0,
            entities: entities.slice(0, 30),
            entityMax: Math.max(1, ...entities.map((x) => x.amount), unallocated),
            unallocated,
            companies,
            bars: this.miniBars(trend, months, picked ? picked.color : "#3b6fe0"),
            accountIds: items.map((a) => a.id),
        };
    }

    setFinder(query) {
        this.state.finderQuery = query;
        this.state.finderGroup = "";
        this.state.finderSelected = null;
        this.saveState();
    }

    selectExpense(id) {
        this.state.finderSelected = this.state.finderSelected === id ? null : id;
    }

    drillExpenses(view) {
        this.openJournalItems([...this.baseDomain(), ["account_id", "in", view.accountIds]], view.title);
    }

    exportFinder() {
        const rows = this.finderMatches.map((a) => [a.code, a.name, a.bucket_name, a.amount, a.prev, a.delta_pct, a.pct_revenue]);
        this.downloadCsv("expenses.csv", ["Code", "Expense", "Group", "Amount", "Previous period", "Change %", "% of revenue"], rows);
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------
    async openJournalItems(domain, name) {
        try {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: name || _t("Journal Items"),
                res_model: "account.move.line",
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
                domain,
                target: "current",
            });
        } catch (error) {
            this.notification.add(_t("You need accounting access rights to open journal items."), { type: "warning" });
        }
    }

    baseDomain() {
        const d = this.state.data;
        return [
            ["parent_state", "=", "posted"],
            ["date", ">=", d.period.date_from],
            ["date", "<=", d.period.date_to],
            ["company_id", "in", d.filters.company_ids],
        ];
    }

    openPurchasing() {
        const id = this.state.data && this.state.data.meta.purchasing_action_id;
        if (id) {
            this.action.doAction(id);
        }
    }

    openConfig(xmlid) {
        this.action.doAction(xmlid);
    }

    async runScan() {
        this.state.busy = true;
        try {
            const res = await this.orm.call("ceo.cost.dashboard.report", "run_smart_scan_direct", []);
            this.notification.add(
                _t("Scanner finished: %s accounts and %s analytic accounts classified.", res.accounts_created + res.accounts_updated, res.analytics_created + res.analytics_updated),
                { type: "success" }
            );
            await this.load();
        } catch (error) {
            this.notification.add((error && error.data && error.data.message) || String(error), { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    printPage() {
        window.print();
    }

    openAlert(alert) {
        if (alert.tab) {
            this.setTab(alert.tab, alert.bucket);
        }
    }

    // ------------------------------------------------------------------
    // CSV export
    // ------------------------------------------------------------------
    downloadCsv(filename, header, rows) {
        const esc = (v) => `"${String(v === null || v === undefined ? "" : v).replace(/"/g, '""')}"`;
        const csv = [header, ...rows].map((r) => r.map(esc).join(",")).join("\r\n");
        const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    exportCompanies() {
        const rows = this.companyRows.map((c) => [
            c.name,
            c.revenue,
            c.cogs,
            c.gross_profit,
            c.gross_margin,
            c.opex,
            c.operating_profit,
            c.other_income,
            c.net_profit,
            c.net_margin,
        ]);
        this.downloadCsv(
            "companies.csv",
            ["Company", "Revenue", "Cost of revenue", "Gross profit", "GM %", "Operating expenses", "Operating profit", "Other income", "Net profit", "Net margin %"],
            rows
        );
    }

}

registry.category("actions").add("executive_company_cost_dashboard_main", ExecutiveCostDashboard);
