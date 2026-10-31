/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class HrPayrollDashboard extends Component {
    static template = "anabtawi_hr_payroll_dashboard.HrPayrollDashboard";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");

        const now = new Date();
        const firstDayThisMonth = new Date(now.getFullYear(), now.getMonth(), 1);
        const lastDayThisMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0);

        this.state = useState({
            activeDashboardTab: "overview",
            dashboardMode: "live",
            period: "this_month",
            date_from: this._formatLocalDate(firstDayThisMonth),
            date_to: this._formatLocalDate(lastDayThisMonth),
            time_from: "",
            time_to: "",
            personaTab: "all",
            payrun_id: 0,
            company_id: 0,
            selectedRootId: null,
            selectedAreaId: null,
            selectedDeptPath: [],
            department_ids: [],
            expandedParents: [],
            expandedTableDeptIds: [],
            tableTreeInitialized: false,
            tableViewMode: "tree",
            searchQuery: "",
            sortKey: "net_salary",
            sortOrder: "desc",
            loading: true,
            exportingExcel: false,
            exportingPptx: false,
            printingPdf: false,
            isBenchmarkMode: false,
            benchmarkBranches: [],
        });

        this.data = useState({
            date_from: "",
            date_to: "",
            time_from: "",
            time_to: "",
            active_persona_tab: "all",
            selected_company_id: 0,
            selected_payrun_id: 0,
            payrun_batches: [],
            all_departments: [],
            structured_departments: [],
            parent_departments: [],
            all_companies: [],
            ceo_analytics: {},
            cfo_analytics: {},
            hr_analytics: {},
            labor_cost_report: [],
            labor_cost_totals: {},
            cost_bridge: {},
            three_month_trend: { m2_label: "M-2", m1_label: "M-1", m0_label: "Current", rows: [] },
            workforce_movement: {},
            executive_insights: { positives: [], attention_points: [], priorities: [] },
            kpis: {},
            departments: [],
            department_tree_rows: [],
            channels: [],
            operational_highlights: {
                scheduled_hours: 0,
                approved_hours: 0,
                extra_ot_hours: 0,
                subtracted_late_hours: 0,
                top_ot_departments: [],
                top_late_departments: [],
                top_headcount_departments: [],
            },
        });

        onWillStart(async () => {
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

    async fetchDashboardData() {
        this.state.loading = true;
        try {
            const res = await this.orm.call(
                "hr.payroll.dashboard",
                "get_dashboard_data",
                [],
                {
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    time_from: this.state.time_from,
                    time_to: this.state.time_to,
                    persona_tab: this.state.personaTab,
                    payrun_id: this.state.payrun_id,
                    company_id: this.state.company_id,
                    department_ids: this.state.department_ids,
                }
            );

            const op = res?.operational_highlights || {};
            this.data.date_from = res?.date_from || this.state.date_from;
            this.data.date_to = res?.date_to || this.state.date_to;
            this.data.time_from = res?.time_from || this.state.time_from;
            this.data.time_to = res?.time_to || this.state.time_to;
            this.data.active_persona_tab = res?.active_persona_tab || this.state.personaTab;
            this.data.selected_company_id = res?.selected_company_id || 0;
            this.data.selected_payrun_id = res?.selected_payrun_id || 0;
            this.data.payrun_batches = res?.payrun_batches || [];
            this.data.all_departments = res?.all_departments || [];
            this.data.structured_departments = res?.structured_departments || res?.parent_departments || [];
            this.data.parent_departments = res?.parent_departments || [];
            this.data.all_companies = res?.all_companies || [];
            this.data.ceo_analytics = res?.ceo_analytics || {};
            this.data.cfo_analytics = res?.cfo_analytics || {};
            this.data.hr_analytics = res?.hr_analytics || {};
            this.data.kpis = res?.kpis || {};
            this.data.departments = res?.departments || [];
            this.data.department_tree_rows = res?.department_tree_rows || [];
            this.data.channels = res?.channels || [];

            // Auto-expand root and second-level departments in the tree table on first load or filter change
            if (!this.state.tableTreeInitialized && this.data.department_tree_rows.length > 0) {
                this.state.expandedTableDeptIds = this.data.department_tree_rows
                    .filter(r => r.has_children && r.level <= 1)
                    .map(r => r.department_id);
                this.state.tableTreeInitialized = true;
            }
            this.data.operational_highlights = {
                scheduled_hours: op.scheduled_hours || 0,
                approved_hours: op.approved_hours || 0,
                extra_ot_hours: op.extra_ot_hours || 0,
                subtracted_late_hours: op.subtracted_late_hours || 0,
                top_ot_departments: op.top_ot_departments || [],
                top_late_departments: op.top_late_departments || [],
                top_headcount_departments: op.top_headcount_departments || [],
                top_sales_present_emp_branches: op.top_sales_present_emp_branches || [],
                top_overtime_cost_branches: op.top_overtime_cost_branches || [],
            };
        } catch (error) {
            console.error("Failed to load HR & Payroll dashboard data", error);
            if (this.notification) {
                this.notification.add(
                    "Error loading dashboard: " + (error.data?.message || error.message || error),
                    { type: "danger" }
                );
            }
        } finally {
            this.state.loading = false;
        }
    }

    setDashboardTab(tab) {
        this.state.activeDashboardTab = tab;
    }

    setDashboardMode(mode) {
        this.state.dashboardMode = mode;
    }

    toggleBenchmarkBranch(bId) {
        const id = parseInt(bId);
        const idx = this.state.benchmarkBranches.indexOf(id);
        if (idx > -1) {
            this.state.benchmarkBranches.splice(idx, 1);
        } else {
            if (this.state.benchmarkBranches.length < 5) {
                this.state.benchmarkBranches.push(id);
            }
        }
    }

    setPersonaTab(tab) {
        this.state.personaTab = tab;
        this.fetchDashboardData();
    }

    setShift(preset) {
        if (preset === "morning") {
            this.state.time_from = "08:00";
            this.state.time_to = "16:00";
        } else if (preset === "evening") {
            this.state.time_from = "16:00";
            this.state.time_to = "00:00";
        } else if (preset === "fullday") {
            this.state.time_from = "00:00";
            this.state.time_to = "23:59";
        }
        this.fetchDashboardData();
    }

    async printExecutivePdf() {
        if (this.state.printingPdf) return;
        this.state.printingPdf = true;

        if (this.notification) {
            this.notification.add(
                "Generating C-Level Executive PDF Briefing Report...",
                { type: "info" }
            );
        }

        try {
            const action = await this.orm.call(
                "hr.payroll.dashboard",
                "action_print_executive_pdf",
                [],
                {
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    payrun_id: this.state.payrun_id,
                    company_id: this.state.company_id,
                    department_ids: this.state.department_ids,
                }
            );

            if (action) {
                await this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to print executive PDF report", error);
            if (this.notification) {
                this.notification.add(
                    "PDF generation failed: " + (error.data?.message || error.message || error),
                    { type: "danger" }
                );
            }
        } finally {
            this.state.printingPdf = false;
        }
    }

    setPeriod(period) {
        this.state.period = period;
        const now = new Date();
        let fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
        let toDate = new Date(now.getFullYear(), now.getMonth() + 1, 0);

        if (period === "today") {
            fromDate = new Date();
            toDate = new Date();
        } else if (period === "this_month") {
            fromDate = new Date(now.getFullYear(), now.getMonth(), 1);
            toDate = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        } else if (period === "prev_month") {
            fromDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
            toDate = new Date(now.getFullYear(), now.getMonth(), 0);
        } else if (period === "this_quarter") {
            const quarterMonth = Math.floor(now.getMonth() / 3) * 3;
            fromDate = new Date(now.getFullYear(), quarterMonth, 1);
            toDate = new Date(now.getFullYear(), quarterMonth + 3, 0);
        } else if (period === "this_year") {
            fromDate = new Date(now.getFullYear(), 0, 1);
            toDate = new Date(now.getFullYear(), 11, 31);
        }

        this.state.date_from = this._formatLocalDate(fromDate);
        this.state.date_to = this._formatLocalDate(toDate);
        this.fetchDashboardData();
    }

    selectCompany(compId) {
        this.state.company_id = parseInt(compId) || 0;
        this.state.selectedRootId = null;
        this.state.selectedAreaId = null;
        this.state.selectedDeptPath = [];
        this.state.department_ids = [];
        this.state.expandedParents = [];
        this.state.tableTreeInitialized = false;
        this.fetchDashboardData();
    }

    isCompanySelected(compId) {
        return (this.state.company_id || 0) === (parseInt(compId) || 0);
    }

    // -------------------------------------------------------------
    // RECURSIVE N-LEVEL DEPARTMENT FILTER NAVIGATION
    // (Matches Odoo's exact Department hierarchy to any depth)
    // -------------------------------------------------------------
    selectRootDepartment(rootId) {
        if (rootId === "all") {
            this.state.selectedRootId = null;
            this.state.selectedAreaId = null;
            this.state.selectedDeptPath = [];
            this.state.department_ids = [];
        } else {
            const rId = parseInt(rootId);
            this.state.selectedRootId = rId;
            this.state.selectedAreaId = null;
            this.state.selectedDeptPath = [rId];
            this.state.department_ids = [rId];
        }
        this.state.tableTreeInitialized = false;
        this.fetchDashboardData();
    }

    selectDepartmentAtLevel(deptNode, level, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        const dId = parseInt(deptNode.id);
        const newPath = this.state.selectedDeptPath.slice(0, level);
        const alreadySelectedAtLevel = this.state.selectedDeptPath[level] === dId;

        if (alreadySelectedAtLevel) {
            // Clicking an already-selected intermediate department steps back up to its parent
            this.state.selectedDeptPath = newPath;
            const parentId = newPath.length > 0 ? newPath[newPath.length - 1] : null;
            this.state.department_ids = parentId ? [parentId] : [];
        } else {
            newPath.push(dId);
            this.state.selectedDeptPath = newPath;
            this.state.department_ids = [dId];
        }
        this.state.selectedRootId = this.state.selectedDeptPath[0] || null;
        this.state.selectedAreaId = this.state.selectedDeptPath[1] || null;
        this.state.tableTreeInitialized = false;
        this.fetchDashboardData();
    }

    toggleLeafDepartment(deptId, parentId, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        const bId = parseInt(deptId);
        const pId = parseInt(parentId);
        let current = [...(this.state.department_ids || [])];

        if (pId && current.includes(pId)) {
            current = [bId];
        } else {
            const idx = current.indexOf(bId);
            if (idx > -1) {
                current.splice(idx, 1);
            } else {
                current.push(bId);
            }
        }

        if (current.length === 0 && pId) {
            current = [pId];
        }

        this.state.department_ids = current;
        this.state.tableTreeInitialized = false;
        this.fetchDashboardData();
    }

    selectAreaDepartment(area) {
        this.selectDepartmentAtLevel(area, 1);
    }

    toggleBranchDepartment(branchId, ev) {
        const parentId = this.state.selectedDeptPath.length > 0
            ? this.state.selectedDeptPath[this.state.selectedDeptPath.length - 1]
            : (this.state.selectedAreaId || this.state.selectedRootId);
        this.toggleLeafDepartment(branchId, parentId, ev);
    }

    selectAllDepartments() {
        this.state.selectedRootId = null;
        this.state.selectedAreaId = null;
        this.state.selectedDeptPath = [];
        this.state.department_ids = [];
        this.state.tableTreeInitialized = false;
        this.fetchDashboardData();
    }

    isRootSelected(rootId) {
        if (rootId === "all") {
            return this.state.selectedDeptPath.length === 0 && (!this.state.department_ids || this.state.department_ids.length === 0);
        }
        return this.state.selectedDeptPath[0] === parseInt(rootId);
    }

    isDeptNodeSelected(deptId, level) {
        const dId = parseInt(deptId);
        if (this.state.selectedDeptPath[level] === dId) {
            return true;
        }
        return (this.state.department_ids || []).includes(dId);
    }

    isAreaSelected(areaId) {
        return this.state.selectedDeptPath[1] === parseInt(areaId);
    }

    isBranchSelected(branchId) {
        const bId = parseInt(branchId);
        if (!this.state.department_ids || this.state.department_ids.length === 0) return true;
        return this.state.department_ids.includes(bId);
    }

    get cascadingDeptTrays() {
        const trays = [];
        let currentList = this.data.structured_departments || [];
        for (let lvl = 0; lvl < this.state.selectedDeptPath.length; lvl++) {
            const selId = this.state.selectedDeptPath[lvl];
            const node = currentList.find(n => n.id === selId);
            if (!node || !node.children || node.children.length === 0) {
                break;
            }
            trays.push({
                level: lvl + 1,
                parentNode: node,
                children: node.children,
                selectedChildId: this.state.selectedDeptPath[lvl + 1] || null,
            });
            currentList = node.children;
        }
        return trays;
    }

    get activeRootData() {
        if (!this.state.selectedRootId || !this.data.structured_departments) return null;
        return this.data.structured_departments.find(r => r.id === this.state.selectedRootId) || null;
    }

    get activeAreaData() {
        const root = this.activeRootData;
        if (!root || !this.state.selectedAreaId || !root.areas) return null;
        return root.areas.find(a => a.id === this.state.selectedAreaId) || null;
    }

    // -------------------------------------------------------------
    // EXPANDABLE HIERARCHICAL TREE TABLE CONTROLS
    // -------------------------------------------------------------
    setTableViewMode(mode) {
        this.state.tableViewMode = mode;
    }

    toggleTableDeptExpand(deptId, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        const dId = parseInt(deptId);
        const idx = this.state.expandedTableDeptIds.indexOf(dId);
        if (idx > -1) {
            this.state.expandedTableDeptIds.splice(idx, 1);
        } else {
            this.state.expandedTableDeptIds.push(dId);
        }
    }

    isTableDeptExpanded(deptId) {
        return this.state.expandedTableDeptIds.includes(parseInt(deptId));
    }

    expandAllTableDepts() {
        const allParentIds = (this.data.department_tree_rows || [])
            .filter(r => r.has_children)
            .map(r => r.department_id);
        this.state.expandedTableDeptIds = [...allParentIds];
    }

    collapseAllTableDepts() {
        this.state.expandedTableDeptIds = [];
    }

    filterByDepartmentFromTable(deptRow, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        const dId = parseInt(deptRow.department_id);
        if (!dId) return;
        const anc = [...(deptRow.ancestor_ids || []), dId];
        this.state.selectedDeptPath = anc;
        this.state.selectedRootId = anc[0] || null;
        this.state.selectedAreaId = anc[1] || null;
        this.state.department_ids = [dId];
        this.state.tableTreeInitialized = false;
        this.fetchDashboardData();
    }

    // Legacy helpers
    toggleParentExpand(parentId, ev) {
        this.toggleTableDeptExpand(parentId, ev);
    }

    isParentExpanded(parentId) {
        return this.isTableDeptExpanded(parentId);
    }

    toggleDepartment(deptId, ev) {
        if (ev) {
            ev.stopPropagation();
        }
        const id = parseInt(deptId);
        const current = [...this.state.department_ids];
        const idx = current.indexOf(id);

        if (idx > -1) {
            current.splice(idx, 1);
        } else {
            current.push(id);
        }
        this.state.department_ids = current;
        this.fetchDashboardData();
    }

    isDeptSelected(deptId) {
        if (deptId === "all") {
            return !this.state.department_ids || this.state.department_ids.length === 0;
        }
        return this.state.department_ids && this.state.department_ids.includes(parseInt(deptId));
    }

    sortBy(key) {
        if (this.state.sortKey === key) {
            this.state.sortOrder = this.state.sortOrder === "asc" ? "desc" : "asc";
        } else {
            this.state.sortKey = key;
            this.state.sortOrder = key === "department_name" ? "asc" : "desc";
        }
    }

    _compareDeptRows(a, b) {
        const key = this.state.sortKey || "net_salary";
        const isAsc = this.state.sortOrder === "asc";
        let valA = a[key];
        let valB = b[key];

        if (typeof valA === "string") {
            valA = (valA || "").toLowerCase();
            valB = (valB || "").toLowerCase();
            return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }

        valA = Number(valA) || 0;
        valB = Number(valB) || 0;
        if (valA !== valB) {
            return isAsc ? valA - valB : valB - valA;
        }
        return (Number(b.headcount) || 0) - (Number(a.headcount) || 0);
    }

    get sortedDepartments() {
        const query = (this.state.searchQuery || "").trim().toLowerCase();
        const treeRows = this.data.department_tree_rows || [];

        // If user selected Hierarchical Tree mode and we have tree rows
        if (this.state.tableViewMode === "tree" && treeRows.length > 0) {
            if (query) {
                // When searching, show all matching nodes (by short_name or complete_name) sorted
                const matched = treeRows.filter(
                    d => (d.complete_name || "").toLowerCase().includes(query)
                        || (d.short_name || "").toLowerCase().includes(query)
                );
                return [...matched].sort((a, b) => this._compareDeptRows(a, b));
            }

            // Group by parent within treeRows to sort siblings at each level while preserving tree hierarchy
            const rowMap = new Map();
            const childrenByParent = new Map();
            const topRoots = [];

            for (const r of treeRows) {
                rowMap.set(r.department_id, r);
            }
            for (const r of treeRows) {
                const pId = r.parent_id && rowMap.has(r.parent_id) ? r.parent_id : 0;
                if (pId === 0) {
                    topRoots.push(r);
                } else {
                    if (!childrenByParent.has(pId)) {
                        childrenByParent.set(pId, []);
                    }
                    childrenByParent.get(pId).push(r);
                }
            }

            topRoots.sort((a, b) => this._compareDeptRows(a, b));
            for (const list of childrenByParent.values()) {
                list.sort((a, b) => this._compareDeptRows(a, b));
            }

            const visibleResult = [];
            const expandedSet = new Set(this.state.expandedTableDeptIds);

            const walk = (node) => {
                visibleResult.push(node);
                if (node.has_children && expandedSet.has(node.department_id)) {
                    const chList = childrenByParent.get(node.department_id) || [];
                    for (const ch of chList) {
                        walk(ch);
                    }
                }
            };

            for (const root of topRoots) {
                walk(root);
            }
            return visibleResult;
        }

        // Flat Leaf View Mode
        let depts = [...(this.data.departments || [])];
        if (query) {
            depts = depts.filter(
                d => (d.department_name || "").toLowerCase().includes(query)
                    || (d.short_name || "").toLowerCase().includes(query)
            );
        }
        depts.sort((a, b) => this._compareDeptRows(a, b));
        return depts;
    }

    get tableSummaryTotals() {
        const query = (this.state.searchQuery || "").toLowerCase().trim();
        let leafDepts = [...(this.data.departments || [])];
        if (query) {
            leafDepts = leafDepts.filter(
                d => (d.department_name || "").toLowerCase().includes(query)
                    || (d.short_name || "").toLowerCase().includes(query)
                    || (d.complete_name || "").toLowerCase().includes(query)
            );
        }
        const totals = {
            headcount: 0,
            payslip_headcount: 0,
            daily_cost: 0,
            basic_salary: 0,
            actual_salary: 0,
            allowances: 0,
            overtime_amount: 0,
            overtime_hours: 0,
            gross_salary: 0,
            deductions: 0,
            social_security_comp: 0,
            net_salary: 0,
            pos_sales: 0,
        };
        for (const d of leafDepts) {
            totals.headcount += Number(d.headcount || 0);
            totals.payslip_headcount += Number(d.payslip_headcount || 0);
            totals.daily_cost += Number(d.daily_cost || 0);
            totals.basic_salary += Number(d.basic_salary || 0);
            totals.actual_salary += Number(d.actual_salary || 0);
            totals.allowances += Number(d.allowances || 0);
            totals.overtime_amount += Number(d.overtime_amount || 0);
            totals.overtime_hours += Number(d.overtime_hours || 0);
            totals.gross_salary += Number(d.gross_salary || 0);
            totals.deductions += Number(d.deductions || 0);
            totals.social_security_comp += Number(d.social_security_comp || 0);
            totals.net_salary += Number(d.net_salary || 0);
            totals.pos_sales += Number(d.pos_sales || 0);
        }
        if (!query && this.data.kpis && this.data.kpis.headcount) {
            totals.headcount = this.data.kpis.headcount;
        }
        return totals;
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

    async onKpiClick(metricType) {
        try {
            const action = await this.orm.call(
                "hr.payroll.dashboard",
                "open_kpi_drilldown",
                [],
                {
                    metric_type: metricType,
                    date_from: this.state.date_from,
                    date_to: this.state.date_to,
                    payrun_id: this.state.payrun_id,
                    company_id: this.state.company_id,
                    department_ids: this.state.department_ids,
                }
            );

            if (action) {
                // Safeguard against missing action.views which causes TypeError in Odoo web client
                if (!action.views && action.view_mode) {
                    action.views = action.view_mode.split(",").map(v => [false, v.trim()]);
                }
                await this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to open HR KPI drilldown action", error);
            if (this.notification) {
                this.notification.add(
                    "Could not open drilldown: " + (error.data?.message || error.message || error),
                    { type: "danger" }
                );
            }
        }
    }

    async exportExcel(reportType = "all") {
        if (this.state.exportingExcel) return;
        this.state.exportingExcel = true;
        const targetScope = (typeof reportType === "string" && reportType) ? reportType : "all";

        if (this.notification) {
            const msgMap = {
                labor_cost: "Generating 6-Sheet Employee Cost & Headcount Excel Report...",
                board_pptx: "Generating 10-Slide Executive Board PowerPoint (.pptx) with Charts & Pies...",
            };
            this.notification.add(
                msgMap[targetScope] || "Generating unified HR & Payroll Excel package...",
                { type: "info" }
            );
        }

        try {
            const wizardVals = {
                date_from: this.state.date_from,
                date_to: this.state.date_to,
                report_type: targetScope,
            };
            if (this.state.payrun_id) {
                wizardVals.payrun_id = this.state.payrun_id;
            }
            if (this.state.company_id) {
                wizardVals.company_id = this.state.company_id;
            }
            if (this.state.department_ids && this.state.department_ids.length > 0) {
                wizardVals.department_ids = [[6, 0, this.state.department_ids.map(Number)]];
            }

            const wizardRes = await this.orm.create("hr.payroll.report.wizard", [wizardVals]);
            const wizardId = Array.isArray(wizardRes) ? wizardRes[0] : wizardRes;

            const methodName = targetScope === "board_pptx" ? "action_export_pptx" : "action_export_xlsx";
            const action = await this.orm.call(
                "hr.payroll.report.wizard",
                methodName,
                [wizardId]
            );

            if (action && action.type === "ir.actions.act_url" && action.url) {
                window.location.href = action.url;
                if (this.notification) {
                    this.notification.add(
                        targetScope === "board_pptx"
                            ? "10-Slide Board PowerPoint (.pptx) downloaded successfully."
                            : "Excel file exported successfully.",
                        { type: "success" }
                    );
                }
            } else if (action) {
                if (!action.views && action.view_mode) {
                    action.views = action.view_mode.split(",").map(v => [false, v.trim()]);
                }
                await this.actionService.doAction(action);
            }
        } catch (error) {
            console.error("Failed to export HR & Payroll report", error);
            if (this.notification) {
                this.notification.add(
                    "Export failed: " + (error.data?.message || error.message || error),
                    { type: "danger" }
                );
            }
        } finally {
            this.state.exportingExcel = false;
        }
    }

    async exportBoardPptx() {
        return this.exportExcel("board_pptx");
    }
}

registry.category("actions").add("hr_payroll_dashboard_main", HrPayrollDashboard);
