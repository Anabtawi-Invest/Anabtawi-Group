# -*- coding: utf-8 -*-
from datetime import datetime, date, timedelta
from collections import defaultdict
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class HrPayrollDashboard(models.AbstractModel):
    _name = "hr.payroll.dashboard"
    _description = "HR & Payroll Executive Dashboard Backend Service"

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None, payrun_id=None, company_id=None, department_ids=None, time_from=None, time_to=None, persona_tab="all"):
        """Calculates and aggregates comprehensive HR, Payroll, Overtime, and Attendance metrics for C-Level executives."""
        self = self.sudo()
        user_companies = self.env.user.company_ids
        target_company_id = int(company_id) if company_id and int(company_id) > 0 else 0

        # Determine date ranges
        today = fields.Date.today()
        if not date_from or not date_to:
            start_date = today.replace(day=1)
            next_month = (start_date + timedelta(days=32)).replace(day=1)
            end_date = next_month - timedelta(days=1)
        else:
            if isinstance(date_from, str):
                start_date = fields.Date.from_string(date_from[:10])
            else:
                start_date = date_from
            if isinstance(date_to, str):
                end_date = fields.Date.from_string(date_to[:10])
            else:
                end_date = date_to

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        if time_from and time_to:
            try:
                h1, m1 = map(int, str(time_from).strip().split(":")[:2])
                h2, m2 = map(int, str(time_to).strip().split(":")[:2])
                start_dt = datetime.combine(start_date, datetime.min.time()).replace(hour=h1, minute=m1)
                end_dt = datetime.combine(end_date, datetime.min.time()).replace(hour=h2, minute=m2)
            except Exception as e:
                _logger.warning("Time range parsing fallback: %s", e)

        # Retrieve payrun batches for dropdown
        payrun_domain = [("company_id", "=", target_company_id)] if target_company_id > 0 else [("company_id", "in", user_companies.ids)]
        payruns = self.env["hr.payslip.run"].search(payrun_domain, order="date_start desc", limit=30)
        payrun_batches = [{
            "id": p.id,
            "name": p.name or _("Batch %s") % p.id,
            "date_start": str(p.date_start or ""),
            "date_end": str(p.date_end or ""),
            "state": p.state if hasattr(p, "state") else "",
        } for p in payruns]

        # Base Domain for Payslips (Includes ALL validated/draft payslips except cancelled)
        slip_domain = [
            ("state", "not in", ["cancel"]),
        ]
        target_payrun_id = int(payrun_id) if payrun_id and int(payrun_id) > 0 else 0
        if target_payrun_id > 0:
            slip_domain.append(("payslip_run_id", "=", target_payrun_id))
            selected_run = self.env["hr.payslip.run"].browse(target_payrun_id).exists()
            if selected_run and selected_run.date_start and selected_run.date_end:
                start_date = selected_run.date_start
                end_date = selected_run.date_end
                start_dt = datetime.combine(start_date, datetime.min.time())
                end_dt = datetime.combine(end_date, datetime.max.time())
        else:
            slip_domain.extend([
                ("date_from", "<=", end_date),
                ("date_to", ">=", start_date),
            ])

        if target_company_id > 0:
            slip_domain.append(("company_id", "=", target_company_id))
        else:
            slip_domain.append(("company_id", "in", user_companies.ids))

        # Resolve selected departments and all their child departments (hierarchical)
        all_target_dep_ids_set = set()
        if department_ids:
            raw_dep_ids = [int(d) for d in department_ids if int(d) > 0]
            if raw_dep_ids:
                all_target_dep_ids = self.env["hr.department"].sudo().search([("id", "child_of", raw_dep_ids)]).ids
                all_target_dep_ids_set = set(all_target_dep_ids)
                slip_domain.extend([
                    "|",
                    ("employee_id.department_id", "in", all_target_dep_ids),
                    ("department_id", "in", all_target_dep_ids),
                ])

        raw_payslips = self.env["hr.payslip"].search(slip_domain)
        # Filter by canonical department (Employee department first, fallback to Payslip/Version department)
        if all_target_dep_ids_set:
            def _canonical_slip_dept_id(s):
                d = (
                    (s.employee_id and s.employee_id.department_id)
                    or s.department_id
                    or (getattr(s, "version_id", False) and s.version_id.department_id)
                )
                return d.id if d else 0
            payslips = raw_payslips.filtered(lambda s: _canonical_slip_dept_id(s) in all_target_dep_ids_set)
        else:
            payslips = raw_payslips

        # Active employees per company for Company Pills & Department Tree Headcounts
        all_user_emps = self.env["hr.employee"].sudo().search([
            ("active", "=", True),
            ("company_id", "in", user_companies.ids),
        ])
        comp_emp_counts = defaultdict(int)
        for e in all_user_emps:
            if e.company_id:
                comp_emp_counts[e.company_id.id] += 1

        # Retrieve allowed companies with employee counts
        allowed_companies = [{
            "id": 0,
            "name": _("All Companies (جميع الشركات)"),
            "emp_count": len(all_user_emps),
        }]
        allowed_companies.extend([
            {
                "id": c.id,
                "name": c.name,
                "emp_count": comp_emp_counts.get(c.id, 0),
            } for c in user_companies
        ])

        # Active employees in the currently selected company scope
        if target_company_id > 0:
            company_active_emps = all_user_emps.filtered(lambda e: e.company_id.id == target_company_id)
        else:
            company_active_emps = all_user_emps

        if all_target_dep_ids_set:
            filtered_active_emps = company_active_emps.filtered(
                lambda e: e.department_id and e.department_id.id in all_target_dep_ids_set
            )
        else:
            filtered_active_emps = company_active_emps

        # Retrieve ALL departments relevant to the company (shared departments + company departments + any department referenced by active employees/payslips)
        dept_domain = [("company_id", "in", [False, target_company_id])] if target_company_id > 0 else [("company_id", "in", [False] + user_companies.ids)]
        base_departments = self.env["hr.department"].sudo().search(dept_domain, order="name asc")
        emp_dept_ids = company_active_emps.mapped("department_id").ids
        slip_dept_ids = (payslips.mapped("employee_id.department_id") | payslips.mapped("department_id")).ids
        extra_dept_ids = list(set(emp_dept_ids + slip_dept_ids) - set(base_departments.ids))
        if extra_dept_ids:
            # Also include ancestors of any extra departments
            extra_with_parents = self.env["hr.department"].sudo().search([("id", "parent_of", extra_dept_ids)])
            raw_departments = (base_departments | extra_with_parents).sorted(key=lambda d: (d.name or ""))
        else:
            raw_departments = base_departments

        raw_dept_dict = {d.id: d for d in raw_departments}

        # Build parent -> direct children map and transitive dept_children_map (child_of in memory)
        direct_children_map = defaultdict(list)
        dept_parent_map = {}
        for d in raw_departments:
            p_id = d.parent_id.id if (d.parent_id and d.parent_id.id in raw_dept_dict) else 0
            dept_parent_map[d.id] = p_id
            direct_children_map[p_id].append(d)

        dept_children_map = defaultdict(set)
        for d in raw_departments:
            curr = d.id
            visited = set()
            while curr and curr not in visited:
                visited.add(curr)
                dept_children_map[curr].add(d.id)
                curr = dept_parent_map.get(curr, 0)

        # Map active employees by their direct department and rolled-up department subtree
        direct_emp_ids_by_dept = defaultdict(set)
        unassigned_active_emp_ids = set()
        for e in company_active_emps:
            if e.department_id and e.department_id.id in raw_dept_dict:
                direct_emp_ids_by_dept[e.department_id.id].add(e.id)
            else:
                unassigned_active_emp_ids.add(e.id)

        subtree_emp_ids_by_dept = {}
        for d in raw_departments:
            s_ids = set()
            for c_id in dept_children_map[d.id]:
                s_ids.update(direct_emp_ids_by_dept.get(c_id, set()))
            subtree_emp_ids_by_dept[d.id] = s_ids

        # Build full recursive N-level Department Tree (never skipping Level 2 or any intermediate level)
        def _build_dept_tree_node(dept_rec, level=0, path_names=None):
            current_path = (path_names or []) + [dept_rec.name or ""]
            full_path_str = " / ".join(current_path)
            children_recs = sorted(direct_children_map.get(dept_rec.id, []), key=lambda x: (x.name or ""))
            children_nodes = [_build_dept_tree_node(ch, level + 1, current_path) for ch in children_recs]
            descendant_dept_count = len(dept_children_map.get(dept_rec.id, set()) - {dept_rec.id})
            return {
                "id": dept_rec.id,
                "name": dept_rec.name or "",
                "complete_name": dept_rec.complete_name or full_path_str,
                "parent_id": dept_parent_map.get(dept_rec.id, 0),
                "company_id": dept_rec.company_id.id if dept_rec.company_id else 0,
                "level": level,
                "direct_emp_count": len(direct_emp_ids_by_dept.get(dept_rec.id, set())),
                "total_emp_count": len(subtree_emp_ids_by_dept.get(dept_rec.id, set())),
                "child_count": len(children_nodes),
                "total_branch_count": descendant_dept_count,
                "children": children_nodes,
                # Legacy compatibility keys for 3-tier consumers:
                "area_count": len(children_nodes),
                "branch_count": len(children_nodes),
                "areas": children_nodes,
                "branches": children_nodes,
            }

        root_deps = sorted(direct_children_map.get(0, []), key=lambda x: (x.name or ""))
        structured_departments = [_build_dept_tree_node(root, level=0) for root in root_deps]

        # Flat department list with complete_name and employee counts for quick lookup
        all_departments_flat = [{
            "id": d.id,
            "name": d.name,
            "complete_name": d.complete_name or d.name,
            "parent_id": dept_parent_map.get(d.id, 0),
            "level": 0,
            "direct_emp_count": len(direct_emp_ids_by_dept.get(d.id, set())),
            "total_emp_count": len(subtree_emp_ids_by_dept.get(d.id, set())),
            "child_ids": [c.id for c in direct_children_map.get(d.id, [])],
        } for d in raw_departments]

        # Determine calendar days in target month vs selected date range
        month_start = start_date.replace(day=1)
        next_month_start = (month_start + timedelta(days=32)).replace(day=1)
        month_total_days = (next_month_start - month_start).days
        if month_total_days <= 0:
            month_total_days = 30

        selected_days = (end_date - start_date).days + 1
        if selected_days <= 0:
            selected_days = 1

        # Exact Payslip Numbers: Do NOT artificially scale/distort payslip amounts when viewing a month or payrun
        proration_ratio = 1.0

        # Aggregate KPI totals
        total_basic_salary = 0.0
        total_actual_salary = 0.0
        total_gross_salary = 0.0
        total_net_salary = 0.0
        total_allowances = 0.0
        total_deductions = 0.0
        total_social_security_emp = 0.0
        total_social_security_comp = 0.0
        total_income_tax = 0.0
        total_overtime_amount = 0.0
        total_overtime_hours = 0.0
        total_lateness_hours = 0.0
        total_lateness_amount = 0.0
        total_scheduled_hours = 0.0
        total_working_days = 0.0
        total_daily_cost = 0.0

        bank_count = 0
        bank_amount = 0.0
        cash_count = 0
        cash_amount = 0.0

        distinct_employee_ids = set()
        department_dict = {}

        # Build POS Config -> HR Department lookup map (Direct link + Normalized Name & Branch Matching)
        pos_config_dept_map = {}
        if "pos.config" in self.env:
            try:
                all_depts = self.env["hr.department"].sudo().search([])
                dept_by_name = {}
                for d in all_depts:
                    clean_name = (d.name or "").strip().lower()
                    dept_by_name[clean_name] = d.id
                    alt_name = clean_name.replace("فرع", "").replace("branch", "").strip()
                    if alt_name and alt_name not in dept_by_name:
                        dept_by_name[alt_name] = d.id

                all_configs = self.env["pos.config"].sudo().search([])
                for cfg in all_configs:
                    d_obj = getattr(cfg, "department_id", False)
                    if d_obj:
                        pos_config_dept_map[cfg.id] = d_obj.id
                    else:
                        cfg_name = (cfg.name or "").strip().lower()
                        if cfg_name in dept_by_name:
                            pos_config_dept_map[cfg.id] = dept_by_name[cfg_name]
                        else:
                            alt_cfg_name = cfg_name.replace("فرع", "").replace("branch", "").strip()
                            if alt_cfg_name in dept_by_name:
                                pos_config_dept_map[cfg.id] = dept_by_name[alt_cfg_name]
                            else:
                                matched_id = 0
                                for d in all_depts:
                                    d_clean = (d.name or "").strip().lower()
                                    if d_clean and (d_clean in cfg_name or cfg_name in d_clean):
                                        matched_id = d.id
                                        break
                                if matched_id:
                                    pos_config_dept_map[cfg.id] = matched_id
            except Exception as e:
                _logger.warning("Failed to build POS Config to Department map: %s", e)

        # Pre-fetch POS Sales & Order Count for retail branches using SQL aggregation (Zero CPU/RAM overhead)
        pos_sales_by_dept = defaultdict(float)
        pos_orders_by_dept = defaultdict(int)
        if "pos.order" in self.env:
            try:
                pos_domain = [
                    ("state", "in", ["paid", "done", "invoiced"]),
                    ("date_order", ">=", start_dt),
                    ("date_order", "<=", end_dt),
                ]
                if target_company_id > 0:
                    pos_domain.append(("company_id", "=", target_company_id))

                pos_grouped = self.env["pos.order"].sudo()._read_group(
                    pos_domain,
                    ["config_id"],
                    ["amount_total:sum", "id:count"]
                )
                for config_obj, total_amt, order_cnt in pos_grouped:
                    cfg_id = config_obj.id if config_obj else 0
                    d_id = pos_config_dept_map.get(cfg_id, 0)
                    if not d_id and config_obj:
                        d_id = getattr(config_obj, "department_id", False)
                        d_id = d_id.id if d_id else 0
                    if d_id:
                        pos_sales_by_dept[d_id] += (total_amt or 0.0)
                        pos_orders_by_dept[d_id] += (order_cnt or 0)
            except Exception as e:
                _logger.warning("POS Order SQL aggregation fallback: %s", e)

        # Pre-fetch Manufacturing Output data for factory lines using SQL aggregation (Zero CPU/RAM overhead)
        mrp_qty_by_dept = defaultdict(float)
        if "mrp.production" in self.env:
            try:
                mrp_domain = [
                    ("state", "=", "done"),
                    ("date_finished", ">=", start_dt),
                    ("date_finished", "<=", end_dt),
                ]
                if target_company_id > 0:
                    mrp_domain.append(("company_id", "=", target_company_id))

                mrp_grouped = self.env["mrp.production"].sudo()._read_group(
                    mrp_domain,
                    ["department_id"],
                    ["qty_produced:sum"]
                )
                for dept_obj, total_qty in mrp_grouped:
                    if dept_obj:
                        mrp_qty_by_dept[dept_obj.id] += (total_qty or 0.0)
            except Exception as e:
                _logger.warning("MRP Production SQL aggregation fallback: %s", e)

        # Pre-fetch payslip lines and worked days in batch (Prevents N+1 database queries)
        if payslips:
            try:
                payslips.mapped("line_ids")
                payslips.mapped("worked_days_line_ids")
            except Exception as e:
                _logger.warning("Payslip batch pre-fetch fallback: %s", e)

        def _init_dept_bucket(d_id, d_short_name, d_complete_name, d_parent_id=0):
            return {
                "department_id": d_id,
                "short_name": d_short_name,
                "complete_name": d_complete_name,
                "department_name": d_complete_name,
                "parent_id": d_parent_id,
                "employee_ids": set(),
                "payslip_count": 0,
                "headcount": 0,
                "active_headcount": len(direct_emp_ids_by_dept.get(d_id, set())) if d_id > 0 else len(unassigned_active_emp_ids),
                "payslip_headcount": 0,
                "basic_salary": 0.0,
                "actual_salary": 0.0,
                "gross_salary": 0.0,
                "net_salary": 0.0,
                "allowances": 0.0,
                "overtime_amount": 0.0,
                "overtime_hours": 0.0,
                "lateness_hours": 0.0,
                "lateness_amount": 0.0,
                "deductions": 0.0,
                "social_security": 0.0,
                "social_security_comp": 0.0,
                "income_tax": 0.0,
                "working_days": 0.0,
                "daily_cost": 0.0,
            }

        # Pre-initialize buckets for all departments in filter scope that have active employees, POS sales, or MRP output
        for d in raw_departments:
            if all_target_dep_ids_set and d.id not in all_target_dep_ids_set:
                continue
            department_dict[d.id] = _init_dept_bucket(
                d.id,
                d.name or _("Unassigned"),
                d.complete_name or d.name or _("Unassigned"),
                dept_parent_map.get(d.id, 0),
            )

        if not all_target_dep_ids_set and unassigned_active_emp_ids:
            department_dict[0] = _init_dept_bucket(
                0,
                _("Unassigned / Other"),
                _("Unassigned / Other"),
                0,
            )

        for slip in payslips:
            emp = slip.employee_id
            if emp:
                distinct_employee_ids.add(emp.id)
            # Prioritize Employee's department (matching Odoo Employees view), fallback to Payslip / Version department
            dep = (
                (emp and emp.department_id)
                or slip.department_id
                or (getattr(slip, "version_id", False) and slip.version_id.department_id)
            )
            dep_id = dep.id if dep else 0
            dep_short_name = dep.name if dep else _("Unassigned / Other")
            dep_complete_name = (dep.complete_name or dep.name) if dep else _("Unassigned / Other")
            dep_parent_id = dept_parent_map.get(dep_id, dep.parent_id.id if (dep and dep.parent_id) else 0)

            if dep_id not in department_dict:
                department_dict[dep_id] = _init_dept_bucket(
                    dep_id,
                    dep_short_name,
                    dep_complete_name,
                    dep_parent_id,
                )

            if emp:
                department_dict[dep_id]["employee_ids"].add(emp.id)
            department_dict[dep_id]["payslip_count"] += 1

            # Contract / Employee Base Wage fallback
            contract_wage = (
                (emp and getattr(emp, "wage", 0.0))
                or getattr(slip, "basic_wage", 0.0)
                or getattr(slip, "wage", 0.0)
                or 0.0
            )
            if not contract_wage and hasattr(slip, "version_id") and slip.version_id:
                if hasattr(slip.version_id, "_get_contract_wage"):
                    contract_wage = slip.version_id._get_contract_wage() or 0.0
                else:
                    contract_wage = getattr(slip.version_id, "contract_wage", 0.0) or getattr(slip.version_id, "wage", 0.0) or 0.0
            elif not contract_wage and hasattr(slip, "contract_id") and slip.contract_id:
                contract_wage = getattr(slip.contract_id, "wage", 0.0) or 0.0

            slip_basic = 0.0
            slip_actual = 0.0
            slip_net = 0.0
            slip_gross = 0.0
            slip_allowances = 0.0
            slip_deductions = 0.0
            slip_ssc_emp = 0.0
            slip_ssc_comp = 0.0
            slip_tax = 0.0
            slip_ot_amount = 0.0
            slip_late_amount = 0.0

            # Worked Days & payroll_fix_recon Attendance Analysis (Exact Hours)
            slip_days = 0.0
            slip_sched_hours = 0.0
            slip_ot_hours = 0.0
            slip_late_hours = 0.0
            slip_wd_ot_amount = 0.0
            slip_wd_late_amount = 0.0

            if hasattr(slip, "worked_days_line_ids") and slip.worked_days_line_ids:
                for wd in slip.worked_days_line_ids:
                    code = ((wd.work_entry_type_id and wd.work_entry_type_id.code) or wd.code or "").upper().strip()
                    name = f"{wd.name or ''} {(wd.work_entry_type_id and wd.work_entry_type_id.name) or ''}".lower()
                    hrs = wd.number_of_hours or 0.0
                    days = wd.number_of_days or 0.0
                    amt = getattr(wd, "amount", 0.0) or 0.0

                    is_ot = (
                        code in ("OVERTIME", "EXTRA", "EXTRA_HOURS", "OT", "OTW", "OTR", "PHO")
                        or any(k in code for k in ["OT", "EXTRA", "OVERTIME"])
                        or any(k in name for k in ["إضافي", "اضافي", "ساعات إضافية", "overtime", "extra"])
                    )
                    is_late = (
                        code in ("LAT", "LATE", "LATENESS", "ABS", "ABSENT")
                        or any(k in code for k in ["LATE", "UNPAID", "ABSENT", "SHORT", "DELAY", "DED_HOURS"])
                        or any(k in name for k in ["تأخير", "تاخير", "خصم ساعات", "غياب", "مغادرة", "lateness", "absent"])
                    )
                    is_out = code in ("OUT", "OUTCON", "OUT_OF_CONTRACT", "TSD") or "out of contract" in name or "خارج العقد" in name

                    if is_ot:
                        slip_ot_hours += hrs
                        if amt > 0:
                            slip_wd_ot_amount += amt
                    elif is_late:
                        slip_late_hours += hrs
                        if amt:
                            slip_wd_late_amount += abs(amt)
                    elif not is_out:
                        slip_days += days
                        slip_sched_hours += hrs if hrs > 0 else (days * 8.0)

            # Check payroll_fix_recon fields if available on hr.payslip
            pfr_ot_hours = float(getattr(slip, "attendance_gross_overtime", 0.0) or getattr(slip, "extra_hours_R", 0.0) or 0.0)
            pfr_late_hours = float(getattr(slip, "attendance_gross_undertime", 0.0) or getattr(slip, "lateness_deducted_cash", 0.0) or 0.0)
            if pfr_ot_hours > slip_ot_hours:
                slip_ot_hours = pfr_ot_hours
            if pfr_late_hours > slip_late_hours:
                slip_late_hours = pfr_late_hours

            # Fallback for scheduled hours if not tracked on lines
            if not slip_sched_hours and slip_days:
                slip_sched_hours = min(slip_days, 30.0) * 8.0
            elif not slip_sched_hours and not slip_days:
                slip_sched_hours = 240.0

            # Salary Rule Line Analysis (Exact Anabtawi rule codes)
            if hasattr(slip, "line_ids") and slip.line_ids:
                for line in slip.line_ids:
                    code = (line.code or "").upper().strip()
                    cat_code = (line.category_id.code or "").upper().strip() if line.category_id else ""
                    cat_name = (line.category_id.name or "").lower().strip() if line.category_id else ""
                    name = (line.name or "").lower().strip()
                    amt = line.total or 0.0

                    is_actual_line = (
                        code in ("FULL_WAGE", "ACTUAL_SALARY", "ACTUAL")
                        or "actual salary" in name
                        or "الراتب الفعلي" in name
                    )
                    is_basic_line = (
                        (code in ("BASIC", "SALARY", "BASE", "WAGE") or cat_code in ("BASIC",) or cat_name in ("basic", "basic salary"))
                        and not is_actual_line
                    )

                    if code == "NET" or cat_code == "NET":
                        slip_net = amt
                        continue
                    if code in ("GROSS", "GRS", "TOTAL_GROSS") or cat_code == "GROSS":
                        slip_gross = amt
                        continue
                    if is_basic_line:
                        slip_basic += amt
                        continue
                    if is_actual_line:
                        slip_actual += amt
                        continue

                    # Overtime Salary Rules (including payroll_fix_recon & termination extra hours)
                    is_ot_line = (
                        code in ("OT_NET", "ETH_NET", "RD-S", "OVERTIME", "GROSS_ATT", "OT_COMP", "EXTRA_HOURS", "TERM_EXTRA", "OT")
                        or any(k in code for k in ["OT", "OVERTIME", "EXTRA"])
                        or any(k in name for k in ["اضافي", "إضافي", "عمل إضافي", "عمل اضافي", "extra hours"])
                    )
                    if is_ot_line and cat_code not in ("DED", "DEDUCTION"):
                        slip_ot_amount += amt
                        continue

                    # Lateness / Undertime Deduction Salary Rules
                    is_late_line = (
                        code in ("DED_UNDERTIME", "LATE", "LATENESS", "DED_HOURS")
                        or any(k in code for k in ["LATE", "UNDERTIME", "DELAY", "SHORTAGE", "DED_HOURS"])
                        or any(k in name for k in ["تأخير", "تاخير", "خصم ساعات", "خصم تأخير", "undertime", "attendance deduction"])
                    )
                    if is_late_line:
                        slip_late_amount += abs(amt)
                        slip_deductions += abs(amt)
                        continue

                    # Social Security Analysis (SSE vs SSC)
                    is_ss_emp = code in ("SSE", "SSCE", "SSC_EMP", "SOC_SEC_EMP") or ("ضمان" in name and "موظف" in name)
                    is_ss_comp = code in ("SSC", "SSCC", "SSC_COMP", "SOC_SEC_COMP") or ("ضمان" in name and ("شركة" in name or "صاحب العمل" in name))
                    is_ss_generic = any(k in code for k in ["SS", "SSC", "GOSI"]) or "ضمان" in name
                    if is_ss_emp or is_ss_comp or is_ss_generic:
                        if is_ss_comp or any(k in code for k in ["COMP", "COMPANY", "ER", "SSCCO", "SSCP"]):
                            slip_ssc_comp += abs(amt)
                        else:
                            slip_ssc_emp += abs(amt)
                        continue

                    # Income Tax
                    is_tax = code in ("INCOME_TAX", "TAX", "IT", "ITAX") or any(k in code for k in ["TAX", "ITAX"]) or "ضريبة" in name
                    if is_tax:
                        slip_tax += abs(amt)
                        continue

                    # Allowances (ALW category or allowance rules, excluding BASIC/ACTUAL/OT/GROSS/NET)
                    is_alw = (
                        cat_code in ("ALW", "ALLOWANCE", "ALW_RECURRING")
                        or "allowance" in cat_name
                        or code in ("ALW", "BONUS", "COMMISSION", "ALLW", "TAKLEEF", "TAKLEF", "TRANS", "HOUSING", "TERM_PTO", "TERM_ANNUAL")
                        or any(k in name for k in ["علاوة", "مكافأة", "مكافاه", "بدل", "تكليف", "تنقل"])
                    )
                    if is_alw:
                        slip_allowances += amt
                        continue

                    # Deductions (DED category or deduction rules/attachments, excluding SS and Tax which are tracked above)
                    is_ded = (
                        cat_code in ("DED", "DEDUCTION")
                        or "deduction" in cat_name
                        or code in ("DED", "LOAN", "COMPANY", "COMLON", "PENALTY", "INS", "ADV", "ADVANCE", "DIFF", "DED_ANNUAL_LEAVE")
                        or any(k in name for k in ["خصم", "سلفة", "قرض", "عقوبة", "جزاء", "تأمين", "تامين", "مخالفة", "city ledger", "ledger"])
                    )
                    if is_ded:
                        slip_deductions += abs(amt)
            else:
                slip_net = getattr(slip, "net_wage", 0.0) or getattr(slip, "total_amount", 0.0) or 0.0
                slip_gross = getattr(slip, "gross_wage", 0.0) or contract_wage

            if not slip_basic:
                slip_basic = contract_wage
            if not slip_actual:
                slip_actual = slip_basic

            # Fallbacks for Overtime Amount if rule didn't compute an amount
            hourly_rate = (slip_basic / 240.0) if slip_basic else 0.0
            if not slip_ot_amount and slip_wd_ot_amount:
                slip_ot_amount = slip_wd_ot_amount

            # Fallbacks for Lateness Amount
            if not slip_late_amount and slip_wd_late_amount:
                slip_late_amount = slip_wd_late_amount
                slip_deductions += slip_late_amount

            # Fallbacks for Gross & Net
            if not slip_gross:
                slip_gross = getattr(slip, "gross_wage", 0.0) or (slip_actual + slip_allowances + slip_ot_amount)
            if not slip_net:
                total_all_deductions = slip_deductions + slip_ssc_emp + slip_tax
                slip_net = getattr(slip, "net_wage", 0.0) or (slip_gross - total_all_deductions)

            # Calendar-Exact Employee Daily Cost (using actual target month days)
            slip_daily_cost = (slip_gross + slip_ssc_comp) / float(month_total_days)

            p_basic = slip_basic
            p_actual = slip_actual
            p_gross = slip_gross
            p_net = slip_net
            p_allowances = slip_allowances
            p_deductions = slip_deductions
            p_ssc_emp = slip_ssc_emp
            p_ssc_comp = slip_ssc_comp
            p_tax = slip_tax
            p_ot_amount = slip_ot_amount
            p_ot_hours = slip_ot_hours
            p_late_hours = slip_late_hours
            p_late_amount = slip_late_amount
            p_sched_hours = slip_sched_hours
            p_working_days = min(slip_days, float(month_total_days)) if slip_days else 0.0

            # Accumulate global totals
            total_basic_salary += p_basic
            total_actual_salary += p_actual
            total_gross_salary += p_gross
            total_net_salary += p_net
            total_allowances += p_allowances
            total_deductions += p_deductions
            total_social_security_emp += p_ssc_emp
            total_social_security_comp += p_ssc_comp
            total_income_tax += p_tax
            total_overtime_amount += p_ot_amount
            total_overtime_hours += p_ot_hours
            total_lateness_hours += p_late_hours
            total_lateness_amount += p_late_amount
            total_scheduled_hours += p_sched_hours
            total_working_days += p_working_days
            total_daily_cost += slip_daily_cost

            # Bank vs Cash Payment analysis
            has_bank = False
            if hasattr(emp, "bank_account_id") and emp.bank_account_id:
                has_bank = True
            elif hasattr(emp, "bank_account_ids") and emp.bank_account_ids:
                has_bank = True

            if has_bank:
                bank_count += 1
                bank_amount += p_net
            else:
                cash_count += 1
                cash_amount += p_net

            # Department direct breakdown accumulation
            dep_row = department_dict[dep_id]
            dep_row["basic_salary"] += p_basic
            dep_row["actual_salary"] += p_actual
            dep_row["gross_salary"] += p_gross
            dep_row["net_salary"] += p_net
            dep_row["allowances"] += p_allowances
            dep_row["deductions"] += p_deductions
            dep_row["social_security"] += p_ssc_emp
            dep_row["social_security_comp"] += p_ssc_comp
            dep_row["income_tax"] += p_tax
            dep_row["overtime_amount"] += p_ot_amount
            dep_row["overtime_hours"] += p_ot_hours
            dep_row["lateness_hours"] += p_late_hours
            dep_row["lateness_amount"] += p_late_amount
            dep_row["working_days"] += p_working_days
            dep_row["daily_cost"] += slip_daily_cost

        # Live Attendance & Attendance-Based Live Labor Cost calculation
        today_present_count = 0
        today_absent_count = 0
        live_present_daily_cost = 0.0
        absence_saved_cost = 0.0
        live_attendance_labor_ratio = 0.0
        sales_per_present_emp = 0.0
        dept_present_map = defaultdict(int)

        is_today = (start_date == end_date == today)
        if "hr.attendance" in self.env:
            try:
                att_domain = [
                    ("check_in", "<=", end_dt),
                    "|",
                    ("check_out", "=", False),
                    ("check_out", ">=", start_dt),
                ]
                if target_company_id > 0:
                    att_domain.append(("employee_id.company_id", "=", target_company_id))
                if all_target_dep_ids_set:
                    att_domain.append(("employee_id.department_id", "in", list(all_target_dep_ids_set)))

                attendances = self.env["hr.attendance"].sudo().search(att_domain)
                present_employees = attendances.mapped("employee_id")
                today_present_count = len(present_employees)

                for emp in present_employees:
                    if emp.department_id:
                        dept_present_map[emp.department_id.id] += 1

                today_absent_count = max(len(filtered_active_emps) - today_present_count, 0)

                # Compute exact live daily cost of PRESENT employees vs ABSENT employees
                avg_wage_fallback = (total_gross_salary / len(distinct_employee_ids)) if distinct_employee_ids else 500.0
                for emp in filtered_active_emps:
                    wage = getattr(emp, "wage", 0.0) or 0.0
                    if not wage and hasattr(emp, "contract_id") and emp.contract_id:
                        wage = getattr(emp.contract_id, "wage", 0.0) or 0.0
                    if not wage:
                        wage = avg_wage_fallback

                    emp_daily_cost = (wage * 1.1425) / float(month_total_days)

                    if emp.id in present_employees.ids:
                        live_present_daily_cost += emp_daily_cost
                    else:
                        absence_saved_cost += emp_daily_cost

                live_present_daily_cost = round(live_present_daily_cost, 3)
                absence_saved_cost = round(absence_saved_cost, 3)

            except Exception as e:
                _logger.warning("Live attendance calculation skipped: %s", e)

        # Finalize direct department metrics & build hierarchical roll-up rows
        direct_metrics_by_id = {}
        for d_id, row in department_dict.items():
            payslip_emp_cnt = len(row["employee_ids"])
            active_emp_cnt = row["active_headcount"]
            # Primary headcount matches active employees on the Employees screen if > 0, else payslip employees
            effective_headcount = active_emp_cnt if active_emp_cnt > 0 else payslip_emp_cnt
            direct_metrics_by_id[d_id] = {
                "department_id": d_id,
                "short_name": row["short_name"],
                "complete_name": row["complete_name"],
                "department_name": row["complete_name"],
                "parent_id": row["parent_id"],
                "employee_ids": set(row["employee_ids"]),
                "payslip_count": row["payslip_count"],
                "active_headcount": active_emp_cnt,
                "payslip_headcount": payslip_emp_cnt,
                "headcount": effective_headcount,
                "present_headcount": dept_present_map.get(d_id, 0),
                "basic_salary": round(row["basic_salary"], 3),
                "actual_salary": round(row["actual_salary"], 3),
                "gross_salary": round(row["gross_salary"], 3),
                "net_salary": round(row["net_salary"], 3),
                "allowances": round(row["allowances"], 3),
                "overtime_amount": round(row["overtime_amount"], 3),
                "overtime_hours": round(row["overtime_hours"], 2),
                "lateness_hours": round(row["lateness_hours"], 2),
                "lateness_amount": round(row["lateness_amount"], 3),
                "deductions": round(row["deductions"], 3),
                "social_security": round(row["social_security"], 3),
                "social_security_comp": round(row["social_security_comp"], 3),
                "income_tax": round(row["income_tax"], 3),
                "working_days": round(row["working_days"], 1),
                "daily_cost": round(row["daily_cost"], 3),
                "pos_sales": round(pos_sales_by_dept.get(d_id, 0.0), 3),
                "pos_orders": pos_orders_by_dept.get(d_id, 0),
                "mrp_qty": round(mrp_qty_by_dept.get(d_id, 0.0), 2),
            }

        def _enrich_ratios(m_dict):
            hc = m_dict["headcount"] or m_dict["payslip_headcount"] or m_dict["active_headcount"] or 0
            p_cnt = m_dict["present_headcount"] or 0
            d_cost = m_dict["daily_cost"] or 0.0
            p_sales = m_dict["pos_sales"] or 0.0
            p_orders = m_dict["pos_orders"] or 0
            m_qty = m_dict["mrp_qty"] or 0.0
            m_dict["calendar_days"] = selected_days
            m_dict["avg_daily_cost_per_emp"] = round(d_cost / hc, 3) if hc else 0.0
            m_dict["sales_per_present_emp"] = round(p_sales / p_cnt, 3) if p_cnt else (round(p_sales / hc, 3) if hc else 0.0)
            m_dict["orders_per_present_emp"] = round(p_orders / p_cnt, 1) if p_cnt else (round(p_orders / hc, 1) if hc else 0.0)
            m_dict["sales_per_total_emp"] = round(p_sales / hc, 3) if hc else 0.0
            period_labor_cost = d_cost * float(selected_days)
            m_dict["pos_labor_cost_pct"] = round((period_labor_cost / p_sales * 100.0), 1) if p_sales else 0.0
            m_dict["sales_per_jod_labor"] = round((p_sales / period_labor_cost), 2) if period_labor_cost else 0.0
            m_dict["labor_cost_per_unit"] = round((period_labor_cost / m_qty), 3) if m_qty else 0.0
            return m_dict

        # Compute rolled-up metrics for every department in scope (summing d_id + all descendants in scope)
        rolled_metrics_by_id = {}
        for d in raw_departments:
            if all_target_dep_ids_set and d.id not in all_target_dep_ids_set:
                continue
            desc_ids = [cid for cid in dept_children_map.get(d.id, {d.id}) if cid in direct_metrics_by_id]
            rolled_slip_emps = set()
            for cid in desc_ids:
                rolled_slip_emps.update(direct_metrics_by_id[cid]["employee_ids"])
            rolled_active_hc = sum(direct_metrics_by_id[cid]["active_headcount"] for cid in desc_ids)
            rolled_slip_hc = len(rolled_slip_emps)
            rolled_hc = rolled_active_hc if rolled_active_hc > 0 else rolled_slip_hc

            vis_children = [
                ch.id for ch in sorted(direct_children_map.get(d.id, []), key=lambda x: (x.name or ""))
                if not all_target_dep_ids_set or ch.id in all_target_dep_ids_set
            ]
            direct_m = direct_metrics_by_id.get(d.id, _init_dept_bucket(d.id, d.name, d.complete_name or d.name))

            r_row = {
                "department_id": d.id,
                "short_name": d.name or "",
                "complete_name": d.complete_name or d.name or "",
                "department_name": d.complete_name or d.name or "",
                "parent_id": dept_parent_map.get(d.id, 0),
                "has_children": bool(vis_children),
                "child_ids": vis_children,
                "active_headcount": rolled_active_hc,
                "payslip_headcount": rolled_slip_hc,
                "headcount": rolled_hc,
                "direct_active_headcount": direct_m["active_headcount"],
                "direct_payslip_headcount": direct_m["payslip_headcount"],
                "payslip_count": sum(direct_metrics_by_id[cid]["payslip_count"] for cid in desc_ids),
                "present_headcount": sum(direct_metrics_by_id[cid]["present_headcount"] for cid in desc_ids),
                "basic_salary": round(sum(direct_metrics_by_id[cid]["basic_salary"] for cid in desc_ids), 3),
                "actual_salary": round(sum(direct_metrics_by_id[cid]["actual_salary"] for cid in desc_ids), 3),
                "gross_salary": round(sum(direct_metrics_by_id[cid]["gross_salary"] for cid in desc_ids), 3),
                "net_salary": round(sum(direct_metrics_by_id[cid]["net_salary"] for cid in desc_ids), 3),
                "allowances": round(sum(direct_metrics_by_id[cid]["allowances"] for cid in desc_ids), 3),
                "overtime_amount": round(sum(direct_metrics_by_id[cid]["overtime_amount"] for cid in desc_ids), 3),
                "overtime_hours": round(sum(direct_metrics_by_id[cid]["overtime_hours"] for cid in desc_ids), 2),
                "lateness_hours": round(sum(direct_metrics_by_id[cid]["lateness_hours"] for cid in desc_ids), 2),
                "lateness_amount": round(sum(direct_metrics_by_id[cid]["lateness_amount"] for cid in desc_ids), 3),
                "deductions": round(sum(direct_metrics_by_id[cid]["deductions"] for cid in desc_ids), 3),
                "social_security": round(sum(direct_metrics_by_id[cid]["social_security"] for cid in desc_ids), 3),
                "social_security_comp": round(sum(direct_metrics_by_id[cid]["social_security_comp"] for cid in desc_ids), 3),
                "income_tax": round(sum(direct_metrics_by_id[cid]["income_tax"] for cid in desc_ids), 3),
                "working_days": round(sum(direct_metrics_by_id[cid]["working_days"] for cid in desc_ids), 1),
                "daily_cost": round(sum(direct_metrics_by_id[cid]["daily_cost"] for cid in desc_ids), 3),
                "pos_sales": round(sum(direct_metrics_by_dept_val for direct_metrics_by_dept_val in (direct_metrics_by_id[cid]["pos_sales"] for cid in desc_ids)), 3),
                "pos_orders": sum(direct_metrics_by_id[cid]["pos_orders"] for cid in desc_ids),
                "mrp_qty": round(sum(direct_metrics_by_id[cid]["mrp_qty"] for cid in desc_ids), 2),
            }
            rolled_metrics_by_id[d.id] = _enrich_ratios(r_row)

        # Build pre-ordered expandable tree rows (Parent -> Child -> Grandchild -> ...)
        # Only include nodes that have active employees, payslips, POS sales, or MRP output in their subtree
        def _is_node_active(d_id):
            rm = rolled_metrics_by_id.get(d_id)
            if not rm:
                return False
            return bool(
                rm["active_headcount"] > 0
                or rm["payslip_headcount"] > 0
                or rm["payslip_count"] > 0
                or rm["net_salary"] != 0
                or rm["gross_salary"] != 0
                or rm["pos_sales"] > 0
                or rm["mrp_qty"] > 0
            )

        department_tree_rows = []
        visited_tree_ids = set()

        def _append_tree_rows(d_id, level=0, ancestor_ids=None):
            if d_id in visited_tree_ids or not _is_node_active(d_id):
                return
            visited_tree_ids.add(d_id)
            rm = dict(rolled_metrics_by_id[d_id])
            anc_list = list(ancestor_ids or [])
            active_children = [cid for cid in rm["child_ids"] if _is_node_active(cid)]
            rm["level"] = level
            rm["ancestor_ids"] = anc_list
            rm["has_children"] = bool(active_children)
            rm["child_ids"] = active_children
            rm["is_leaf"] = not bool(active_children)
            department_tree_rows.append(rm)
            for cid in active_children:
                _append_tree_rows(cid, level + 1, anc_list + [d_id])

        # Determine top-level starting nodes for the current filter
        tree_root_ids = [
            d_id for d_id in rolled_metrics_by_id
            if dept_parent_map.get(d_id, 0) not in rolled_metrics_by_id
        ]
        # Sort root nodes by active headcount / net salary descending
        tree_root_ids.sort(
            key=lambda x: (
                rolled_metrics_by_id[x]["net_salary"],
                rolled_metrics_by_id[x]["headcount"],
                rolled_metrics_by_id[x]["short_name"],
            ),
            reverse=True,
        )
        for r_id in tree_root_ids:
            _append_tree_rows(r_id, level=0, ancestor_ids=[])

        # Also build flat direct/leaf department list (for non-duplicated charts, PDF, and flat sorting)
        department_list = []
        for d_id, dm in direct_metrics_by_id.items():
            has_direct_activity = (
                dm["active_headcount"] > 0
                or dm["payslip_headcount"] > 0
                or dm["payslip_count"] > 0
                or dm["net_salary"] != 0
                or dm["gross_salary"] != 0
                or dm["pos_sales"] > 0
                or dm["mrp_qty"] > 0
            )
            if not has_direct_activity:
                continue
            flat_row = dict(dm)
            flat_row.pop("employee_ids", None)
            flat_row["level"] = 0
            flat_row["has_children"] = False
            flat_row["is_leaf"] = True
            _enrich_ratios(flat_row)
            department_list.append(flat_row)

            # If Unassigned (0) has activity, also append it to department_tree_rows
            if d_id == 0:
                unassigned_tree_row = dict(flat_row)
                unassigned_tree_row["ancestor_ids"] = []
                unassigned_tree_row["child_ids"] = []
                department_tree_rows.append(unassigned_tree_row)

        department_list.sort(key=lambda x: (x["net_salary"], x["headcount"]), reverse=True)

        top_ot_departments = sorted(department_list, key=lambda x: x["overtime_hours"], reverse=True)[:5]
        top_late_departments = sorted(department_list, key=lambda x: x["lateness_hours"], reverse=True)[:5]
        top_headcount_departments = sorted(department_list, key=lambda x: x["headcount"], reverse=True)[:5]
        top_sales_present_emp_branches = sorted([d for d in department_list if d["pos_sales"] > 0], key=lambda x: x["sales_per_present_emp"], reverse=True)[:5]
        top_overtime_cost_branches = sorted([d for d in department_list if d["overtime_amount"] > 0], key=lambda x: x["overtime_amount"], reverse=True)[:5]

        approved_hours = max(total_scheduled_hours + total_overtime_hours - total_lateness_hours, 0.0)
        total_employer_payroll_expense = round(total_gross_salary + total_social_security_comp, 3)
        overtime_cost_ratio = round((total_overtime_amount / total_gross_salary * 100.0), 1) if total_gross_salary else 0.0

        total_pos_sales_all = sum(d["pos_sales"] for d in department_list)
        if total_pos_sales_all > 0:
            live_attendance_labor_ratio = round((live_present_daily_cost / total_pos_sales_all * 100.0), 1)
        if today_present_count > 0:
            sales_per_present_emp = round(total_pos_sales_all / today_present_count, 2)

        # C-Level Persona Analytics
        total_pos_sales = total_pos_sales_all
        ceo_sales_labor_roi = round((total_pos_sales / total_employer_payroll_expense), 2) if total_employer_payroll_expense else 0.0

        retail_depts = [d for d in department_list if d["pos_sales"] > 0]
        top_profitable_branches = sorted(retail_depts, key=lambda x: x["sales_per_jod_labor"], reverse=True)[:3]
        bottom_profitable_branches = sorted(retail_depts, key=lambda x: x["pos_labor_cost_pct"], reverse=True)[:3]

        factory_depts = [d for d in department_list if d["mrp_qty"] > 0]
        factory_unit_cost_avg = round(sum(d["labor_cost_per_unit"] for d in factory_depts) / len(factory_depts), 3) if factory_depts else 0.0

        active_emp_total_count = len(filtered_active_emps)
        payslip_emp_total_count = len(distinct_employee_ids)
        effective_kpi_headcount = active_emp_total_count if active_emp_total_count > 0 else payslip_emp_total_count

        cfo_metrics = {
            "total_employer_expense": total_employer_payroll_expense,
            "total_net_cash_outflow": round(total_net_salary, 3),
            "social_security_total_liability": round(total_social_security_emp + total_social_security_comp, 3),
            "tax_liability": round(total_income_tax, 3),
            "bank_disbursement_pct": round((bank_amount / total_net_salary * 100), 1) if total_net_salary else 0.0,
            "cash_disbursement_pct": round((cash_amount / total_net_salary * 100), 1) if total_net_salary else 0.0,
        }

        hr_metrics = {
            "is_today": is_today,
            "today_present_count": today_present_count,
            "today_absent_count": today_absent_count,
            "live_present_daily_cost": live_present_daily_cost,
            "absence_saved_cost": absence_saved_cost,
            "live_attendance_labor_ratio": live_attendance_labor_ratio,
            "sales_per_present_emp": sales_per_present_emp,
            "overtime_cost_ratio": overtime_cost_ratio,
            "lateness_hours_total": round(total_lateness_hours, 1),
            "avg_salary_per_emp": round(total_net_salary / payslip_emp_total_count, 3) if payslip_emp_total_count else 0.0,
        }

        data = {
            "date_from": str(start_date),
            "date_to": str(end_date),
            "time_from": time_from or "",
            "time_to": time_to or "",
            "active_persona_tab": persona_tab or "all",
            "calendar_days": selected_days,
            "selected_company_id": target_company_id,
            "selected_payrun_id": int(payrun_id) if payrun_id else 0,
            "payrun_batches": payrun_batches,
            "all_departments": all_departments_flat,
            "structured_departments": structured_departments,
            "parent_departments": structured_departments,
            "all_companies": allowed_companies,
            "ceo_analytics": {
                "sales_labor_roi": ceo_sales_labor_roi,
                "total_pos_sales": round(total_pos_sales, 3),
                "top_profitable_branches": top_profitable_branches,
                "bottom_profitable_branches": bottom_profitable_branches,
                "factory_unit_cost_avg": factory_unit_cost_avg,
            },
            "cfo_analytics": cfo_metrics,
            "hr_analytics": hr_metrics,
            "kpis": {
                "total_net_salary": round(total_net_salary, 3),
                "total_gross_salary": round(total_gross_salary, 3),
                "total_basic_salary": round(total_basic_salary, 3),
                "total_actual_salary": round(total_actual_salary, 3),
                "total_allowances": round(total_allowances, 3),
                "total_deductions": round(total_deductions, 3),
                "total_social_security": round(total_social_security_emp, 3),
                "total_social_security_company": round(total_social_security_comp, 3),
                "total_income_tax": round(total_income_tax, 3),
                "total_overtime_amount": round(total_overtime_amount, 3),
                "total_overtime_hours": round(total_overtime_hours, 2),
                "total_lateness_hours": round(total_lateness_hours, 2),
                "total_lateness_amount": round(total_lateness_amount, 3),
                "total_working_days": round(total_working_days, 1),
                "headcount": effective_kpi_headcount,
                "active_headcount": active_emp_total_count,
                "payslip_headcount": payslip_emp_total_count,
                "payslip_count": len(payslips),
                "bank_count": bank_count,
                "bank_amount": round(bank_amount, 3),
                "cash_count": cash_count,
                "cash_amount": round(cash_amount, 3),
                "avg_salary_per_emp": round(total_net_salary / payslip_emp_total_count, 3) if payslip_emp_total_count else 0.0,
                "total_daily_cost": round(total_daily_cost, 3),
                "avg_daily_cost_per_emp": round(total_daily_cost / payslip_emp_total_count, 3) if payslip_emp_total_count else 0.0,
                "total_employer_expense": total_employer_payroll_expense,
                "overtime_cost_ratio": overtime_cost_ratio,
                "live_present_daily_cost": live_present_daily_cost,
                "absence_saved_cost": absence_saved_cost,
                "live_attendance_labor_ratio": live_attendance_labor_ratio,
                "sales_per_present_emp": sales_per_present_emp,
                "pos_orders_count": sum(pos_orders_by_dept.values()),
                "orders_per_present_emp": round((sum(pos_orders_by_dept.values()) / today_present_count), 1) if today_present_count else 0.0,
            },
            "departments": department_list,
            "department_tree_rows": department_tree_rows,
            "channels": [
                {
                    "name": _("Bank Transfer (تحويل بنكي)"),
                    "count": bank_count,
                    "amount": round(bank_amount, 3),
                    "percentage": round((bank_amount / total_net_salary * 100), 1) if total_net_salary else 0.0,
                    "color": "#3b82f6",
                },
                {
                    "name": _("Cash / Direct Payment (نقدي)"),
                    "count": cash_count,
                    "amount": round(cash_amount, 3),
                    "percentage": round((cash_amount / total_net_salary * 100), 1) if total_net_salary else 0.0,
                    "color": "#10b981",
                },
            ],
            "operational_highlights": {
                "scheduled_hours": round(total_scheduled_hours, 2),
                "approved_hours": round(approved_hours, 2),
                "extra_ot_hours": round(total_overtime_hours, 2),
                "subtracted_late_hours": round(total_lateness_hours, 2),
                "top_ot_departments": top_ot_departments,
                "top_late_departments": top_late_departments,
                "top_headcount_departments": top_headcount_departments,
                "top_sales_present_emp_branches": top_sales_present_emp_branches,
                "top_overtime_cost_branches": top_overtime_cost_branches,
            }
        }
        return data


    @api.model
    def open_kpi_drilldown(self, metric_type, date_from=None, date_to=None, payrun_id=None, company_id=None, department_ids=None):
        """Returns window action with pre-filtered domain and explicit views array for Odoo 19 web client."""
        user_companies = self.env.user.company_ids
        target_company_id = int(company_id) if company_id and int(company_id) > 0 else 0

        today = fields.Date.today()
        if not date_from or not date_to:
            start_date = today.replace(day=1)
            next_month = (start_date + timedelta(days=32)).replace(day=1)
            end_date = next_month - timedelta(days=1)
        else:
            start_date = fields.Date.from_string(date_from[:10]) if isinstance(date_from, str) else date_from
            end_date = fields.Date.from_string(date_to[:10]) if isinstance(date_to, str) else date_to

        slip_domain = [
            ("state", "not in", ["cancel"]),
        ]
        target_payrun_id = int(payrun_id) if payrun_id and int(payrun_id) > 0 else 0
        if target_payrun_id > 0:
            slip_domain.append(("payslip_run_id", "=", target_payrun_id))
        else:
            slip_domain.extend([
                ("date_from", "<=", end_date),
                ("date_to", ">=", start_date),
            ])

        if target_company_id > 0:
            slip_domain.append(("company_id", "=", target_company_id))
        else:
            slip_domain.append(("company_id", "in", user_companies.ids))

        all_target_dep_ids = []
        if department_ids:
            raw_dep_ids = [int(d) for d in department_ids if int(d) > 0]
            if raw_dep_ids:
                all_target_dep_ids = self.env["hr.department"].sudo().search([("id", "child_of", raw_dep_ids)]).ids
                slip_domain.extend([
                    "|",
                    ("employee_id.department_id", "in", all_target_dep_ids),
                    ("department_id", "in", all_target_dep_ids),
                ])

        raw_payslips = self.env["hr.payslip"].search(slip_domain)
        if all_target_dep_ids:
            target_set = set(all_target_dep_ids)
            payslips = raw_payslips.filtered(
                lambda s: (
                    (
                        (s.employee_id and s.employee_id.department_id)
                        or s.department_id
                        or (getattr(s, "version_id", False) and s.version_id.department_id)
                    ).id in target_set
                ) if (
                    (s.employee_id and s.employee_id.department_id)
                    or s.department_id
                    or (getattr(s, "version_id", False) and s.version_id.department_id)
                ) else False
            )
        else:
            payslips = raw_payslips
        slip_ids = payslips.ids

        if metric_type == "headcount":
            emp_domain = [("active", "=", True)]
            if target_company_id > 0:
                emp_domain.append(("company_id", "=", target_company_id))
            else:
                emp_domain.append(("company_id", "in", user_companies.ids))
            if all_target_dep_ids:
                emp_domain.append(("department_id", "in", all_target_dep_ids))
            active_emp_ids = self.env["hr.employee"].sudo().search(emp_domain).ids
            emp_ids = active_emp_ids if active_emp_ids else payslips.mapped("employee_id").ids
            return {
                "name": _("Active Employees (%s)") % len(emp_ids),
                "type": "ir.actions.act_window",
                "res_model": "hr.employee",
                "view_mode": "list,kanban,form",
                "views": [[False, "list"], [False, "kanban"], [False, "form"]],
                "domain": [("id", "in", emp_ids)],
                "context": {"create": False},
                "target": "current",
            }

        elif metric_type in ["overtime", "overtime_hours", "overtime_amount"]:
            return {
                "name": _("Overtime & Extra Hours Analysis"),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip.worked_days",
                "view_mode": "list,pivot,graph",
                "views": [[False, "list"], [False, "pivot"], [False, "graph"]],
                "domain": [
                    ("payslip_id", "in", slip_ids),
                    "|", "|",
                    ("code", "ilike", "OT"),
                    ("code", "ilike", "EXTRA"),
                    ("name", "ilike", "إضافي"),
                ],
                "context": {"create": False},
                "target": "current",
            }

        elif metric_type in ["lateness", "lateness_hours", "lateness_amount"]:
            return {
                "name": _("Lateness & Subtracted Hours Analysis"),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip.worked_days",
                "view_mode": "list,pivot,graph",
                "views": [[False, "list"], [False, "pivot"], [False, "graph"]],
                "domain": [
                    ("payslip_id", "in", slip_ids),
                    "|", "|",
                    ("code", "ilike", "LATE"),
                    ("name", "ilike", "تأخير"),
                    ("name", "ilike", "خصم"),
                ],
                "context": {"create": False},
                "target": "current",
            }

        elif metric_type in ["social_security", "social_security_company"]:
            return {
                "name": _("Social Security Deduction Lines"),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip.line",
                "view_mode": "list,pivot,graph",
                "views": [[False, "list"], [False, "pivot"], [False, "graph"]],
                "domain": [
                    ("slip_id", "in", slip_ids),
                    "|", "|",
                    ("code", "ilike", "SS"),
                    ("code", "ilike", "SSC"),
                    ("name", "ilike", "ضمان"),
                ],
                "context": {"create": False},
                "target": "current",
            }

        elif metric_type == "tax":
            return {
                "name": _("Income Tax Deduction Lines"),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip.line",
                "view_mode": "list,pivot,graph",
                "views": [[False, "list"], [False, "pivot"], [False, "graph"]],
                "domain": [
                    ("slip_id", "in", slip_ids),
                    "|",
                    ("code", "ilike", "TAX"),
                    ("name", "ilike", "ضريبة"),
                ],
                "context": {"create": False},
                "target": "current",
            }

        elif metric_type in ["allowances", "deductions"]:
            cat_code = "ALW" if metric_type == "allowances" else "DED"
            return {
                "name": _("Salary %s Lines") % metric_type.capitalize(),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip.line",
                "view_mode": "list,pivot,graph",
                "views": [[False, "list"], [False, "pivot"], [False, "graph"]],
                "domain": [
                    ("slip_id", "in", slip_ids),
                    ("category_id.code", "=", cat_code),
                ],
                "context": {"create": False},
                "target": "current",
            }

        elif metric_type == "bank_transfers":
            bank_slip_ids = payslips.filtered(
                lambda s: bool(s.employee_id.bank_account_id or getattr(s.employee_id, "bank_account_ids", False))
            ).ids
            return {
                "name": _("Bank Transfer Payslips"),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip",
                "view_mode": "list,kanban,form",
                "views": [[False, "list"], [False, "kanban"], [False, "form"]],
                "domain": [("id", "in", bank_slip_ids)],
                "context": {"create": False},
                "target": "current",
            }

        return {
            "name": _("Executive Payslips Drilldown"),
            "type": "ir.actions.act_window",
            "res_model": "hr.payslip",
            "view_mode": "list,kanban,pivot,graph,form",
            "views": [[False, "list"], [False, "kanban"], [False, "pivot"], [False, "graph"], [False, "form"]],
            "domain": [("id", "in", slip_ids)],
            "context": {"create": False},
            "target": "current",
        }

    @api.model
    def action_print_executive_pdf(self, date_from=None, date_to=None, payrun_id=None, company_id=None, department_ids=None):
        """Generates C-level Executive Briefing PDF Action."""
        dashboard_data = self.get_dashboard_data(
            date_from=date_from,
            date_to=date_to,
            payrun_id=payrun_id,
            company_id=company_id,
            department_ids=department_ids,
        )
        return self.env.ref("anabtawi_hr_payroll_dashboard.action_report_executive_payroll_pdf").report_action(
            [], data={"data": dashboard_data}
        )


class PosConfigInheritDashboard(models.Model):
    _inherit = "pos.config"

    department_id = fields.Many2one(
        "hr.department",
        string="HR Department / Branch",
        help="Link this Point of Sale shop/register to an HR Department for executive sales & labor cost reporting."
    )
