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
        total_eos_amount = 0.0
        total_health_ins_comp = 0.0
        eos_slip_count = 0

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
                "eos_amount": 0.0,
                "health_ins_comp": 0.0,
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
            slip_eos_amount = 0.0
            slip_health_ins_comp = 0.0
            slip_has_med_ins = False

            struct_name_low = ((slip.struct_id and slip.struct_id.name) or "").lower()
            is_termination_slip = (
                "termination" in struct_name_low
                or "مخالصة" in struct_name_low
                or bool(getattr(slip, "is_termination", False))
            )

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

                    # End of Service / Termination Settlements (EOS / مخالصة)
                    is_eos_line = (
                        code in ("EOS", "EOSB", "END_OF_SERVICE", "INDEMNITY", "TERM_PTO", "TERM_ANNUAL", "CLEAR_ANNUAL", "CLEAR_PTO")
                        or any(k in code for k in ["EOS", "INDEMNITY", "TERM_"])
                        or any(k in name for k in ["نهاية الخدمة", "نهاية خدمة", "مخالصة", "termination", "end of service"])
                    )
                    if is_eos_line and cat_code not in ("DED", "DEDUCTION"):
                        slip_eos_amount += abs(amt)
                        slip_allowances += amt
                        continue

                    # Company Medical Insurance Share
                    is_med_comp = (
                        code in ("MED_COMP", "INS_COMP", "HEALTH_COMP")
                        or ("تأمين صحي" in name and ("شركة" in name or "صاحب العمل" in name))
                    )
                    if is_med_comp:
                        slip_health_ins_comp += abs(amt)
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
                    if code == "INS" or "تأمين صحي" in name or "تامين صحي" in name or "medical" in name or "health" in name:
                        if abs(amt) > 0:
                            slip_has_med_ins = True
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

            if not slip_health_ins_comp and slip_has_med_ins:
                slip_health_ins_comp = 13.0

            if is_termination_slip:
                eos_slip_count += 1
                if not slip_eos_amount:
                    # On a termination slip, any extra settlement beyond normal actual salary is termination/EOS settlement
                    slip_eos_amount = max(slip_allowances + slip_ot_amount, 0.0)
            elif slip_eos_amount > 0:
                eos_slip_count += 1

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
            total_eos_amount += slip_eos_amount
            total_health_ins_comp += slip_health_ins_comp

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
            dep_row["eos_amount"] += slip_eos_amount
            dep_row["health_ins_comp"] += slip_health_ins_comp

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
                "eos_amount": round(row.get("eos_amount", 0.0), 3),
                "health_ins_comp": round(row.get("health_ins_comp", 0.0), 3),
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
                "eos_amount": round(sum(direct_metrics_by_id[cid].get("eos_amount", 0.0) for cid in desc_ids), 3),
                "health_ins_comp": round(sum(direct_metrics_by_id[cid].get("health_ins_comp", 0.0) for cid in desc_ids), 3),
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

        # Board Workforce Movement, SBU Labor Cost Report, Cost Bridge (Excl. EOS), and 3-Month Rolling Trend
        wf_analytics = self._compute_workforce_and_labor_cost_analytics(
            start_date=start_date,
            end_date=end_date,
            target_company_id=target_company_id,
            user_companies=user_companies,
            all_target_dep_ids_set=all_target_dep_ids_set,
            current_payslips=payslips,
            filtered_active_emps=filtered_active_emps,
            total_basic_salary=total_basic_salary,
            total_allowances=total_allowances,
            total_overtime_amount=total_overtime_amount,
            total_social_security_emp=total_social_security_emp,
            total_social_security_comp=total_social_security_comp,
            total_health_ins_comp=total_health_ins_comp,
            total_eos_amount=total_eos_amount,
            eos_slip_count=eos_slip_count,
            effective_kpi_headcount=effective_kpi_headcount,
        )

        selected_company_name = _("All Companies (جميع الشركات)")
        if target_company_id > 0:
            for comp_item in allowed_companies:
                if comp_item.get("id") == target_company_id:
                    selected_company_name = comp_item.get("name") or selected_company_name
                    break

        data = {
            "date_from": str(start_date),
            "date_to": str(end_date),
            "time_from": time_from or "",
            "time_to": time_to or "",
            "active_persona_tab": persona_tab or "all",
            "calendar_days": selected_days,
            "selected_company_id": target_company_id,
            "selected_company_name": selected_company_name,
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
            "labor_cost_report": wf_analytics["labor_cost_report"],
            "labor_cost_totals": wf_analytics["labor_cost_totals"],
            "cost_bridge": wf_analytics["cost_bridge"],
            "three_month_trend": wf_analytics["three_month_trend"],
            "workforce_movement": wf_analytics["workforce_movement"],
            "executive_insights": wf_analytics["executive_insights"],
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
                "total_eos_amount": round(wf_analytics["cost_bridge"]["eos_settlement_cost"], 3),
                "total_health_ins_company": round(wf_analytics["labor_cost_totals"]["health_ins_comp"], 3),
                "underlying_workforce_cost": round(wf_analytics["cost_bridge"]["underlying_workforce_cost"], 3),
                "underlying_avg_cost_per_emp": round(wf_analytics["cost_bridge"]["underlying_avg_cost_per_emp"], 3),
                "eos_slip_count": wf_analytics["cost_bridge"]["eos_slip_count"],
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

        elif metric_type == "eos":
            eos_slip_ids = payslips.filtered(
                lambda s: (
                    "termination" in ((s.struct_id and s.struct_id.name) or "").lower()
                    or "مخالصة" in ((s.struct_id and s.struct_id.name) or "").lower()
                    or bool(getattr(s, "is_termination", False))
                    or any(
                        (l.code or "").upper() in ("EOS", "EOSB", "END_OF_SERVICE", "INDEMNITY", "TERM_PTO", "TERM_ANNUAL", "CLEAR_ANNUAL", "CLEAR_PTO")
                        or "نهاية الخدمة" in (l.name or "")
                        or "مخالصة" in (l.name or "")
                        for l in getattr(s, "line_ids", [])
                    )
                )
            ).ids
            return {
                "name": _("End-of-Service & Termination Payslips (%s)") % len(eos_slip_ids),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip",
                "view_mode": "list,kanban,form",
                "views": [[False, "list"], [False, "kanban"], [False, "form"]],
                "domain": [("id", "in", eos_slip_ids)],
                "context": {"create": False},
                "target": "current",
            }

        elif metric_type in ["new_hires", "separations"]:
            all_emps_unfiltered = self.env["hr.employee"].with_context(active_test=False).sudo().search(
                [("company_id", "=", target_company_id)] if target_company_id > 0 else [("company_id", "in", user_companies.ids)]
            )
            if all_target_dep_ids:
                t_set = set(all_target_dep_ids)
                all_emps_unfiltered = all_emps_unfiltered.filtered(lambda e: e.department_id and e.department_id.id in t_set)
            matched_ids = []
            for e in all_emps_unfiltered:
                info = self._get_emp_hire_and_sep_info(e)
                if metric_type == "new_hires" and info["hire_date"] and start_date <= info["hire_date"] <= end_date:
                    matched_ids.append(e.id)
                elif metric_type == "separations" and info["sep_date"] and start_date <= info["sep_date"] <= end_date:
                    matched_ids.append(e.id)
            title = _("New Hires (%s)") % len(matched_ids) if metric_type == "new_hires" else _("Separations / Exits (%s)") % len(matched_ids)
            return {
                "name": title,
                "type": "ir.actions.act_window",
                "res_model": "hr.employee",
                "view_mode": "list,kanban,form",
                "views": [[False, "list"], [False, "kanban"], [False, "form"]],
                "domain": [("id", "in", matched_ids)],
                "context": {"active_test": False, "create": False},
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

    # =========================================================================
    # BOARD WORKFORCE MOVEMENT, SBU LABOR COST & 3-MONTH ROLLING TREND ENGINE
    # =========================================================================
    @api.model
    def _classify_sbu_key(self, emp=None, dep=None, comp=None):
        """
        Classifies an employee/department/company into one of the 5 Strategic Business Units
        from `Employee Cost.xlsx` and `HR Dashboard July-2026.pptx`:
          1. 'united'        -> شركة الوحدة (United)
          2. 'delta_factory' -> شركة دلتا (المصنع) (Delta Factory)
          3. 'admin'         -> الادارة (Head Office / Administration)
          4. 'retail_amman'  -> Retail Amman (فروع عمان والمحافظات)
          5. 'retail_alhadaf'-> Retail Alhadaf / Aqaba (فروع العقبة - الهدف)
        """
        if not dep and emp:
            dep = emp.department_id
        if not comp and emp:
            comp = emp.company_id
        if not comp and dep:
            comp = dep.company_id

        comp_name = ((comp and comp.name) or "").lower()
        dep_path = ((dep and (dep.complete_name or dep.name)) or "").lower()

        # 1. United Company
        if any(k in comp_name for k in ["united", "الوحدة", "متحدة", "المتحدة"]):
            return "united"

        # 2. Retail Alhadaf / Aqaba (Company Al Hadaf OR Region 5 / Aqaba branches)
        if any(k in comp_name for k in ["hadaf", "الهدف", "هدف"]) or any(
            k in dep_path for k in ["منطقة 5", "العقبة", "ايلا", "aqaba", "hadaf", "الهدف"]
        ):
            return "retail_alhadaf"

        # 3. Retail Amman (Branches Admin / الفروع / Retail / Regions 1-4)
        is_retail_branch = any(
            k in dep_path
            for k in [
                "branches admin",
                "ادارة الفروع",
                "إدارة الفروع",
                "الفروع",
                "فرع",
                "منطقة 1",
                "منطقة 2",
                "منطقة 3",
                "منطقة 4",
                "retail",
            ]
        )
        if is_retail_branch and not any(
            k in dep_path
            for k in ["المالية", "الموارد البشرية", "تكنولوجيا المعلومات", "القانونية", "تطوير الاعمال", "الادارة العليا"]
        ):
            return "retail_amman"

        # 4. Head Office / Administration (الادارة / المالية / الموارد البشرية / تكنولوجيا المعلومات / الادارة العليا / التسويق / التصدير)
        is_admin = any(
            k in dep_path
            for k in [
                "الادارة",
                "الإدارة",
                "administration",
                "المالية",
                "accounting",
                "الموارد البشرية",
                "تكنولوجيا المعلومات",
                "القانونية",
                "تطوير الاعمال",
                "الادارة العليا",
                "التسويق",
                "marketing",
                "التصدير",
                "exports",
                "e-commerce",
                "local sales",
                "مبيعات",
            ]
        )
        if is_admin and "المصنع" not in dep_path and "الانتاج" not in dep_path:
            return "admin"

        # 5. Delta Factory (المصنع / Factory / الانتاج / الصيانة / سلسلة التزويد)
        if any(
            k in dep_path
            for k in ["المصنع", "الانتاج", "الإنتاج", "الصيانة", "سلسلة التزويد", "الخدمات العامة", "research", "factory"]
        ):
            return "delta_factory"

        # Fallback by company name
        if any(k in comp_name for k in ["najeeb", "نجيب", "delta", "دلتا", "factory"]):
            return "delta_factory"
        if any(k in comp_name for k in ["invest", "استثمار"]):
            return "retail_amman"
        return "delta_factory"

    @api.model
    def _get_emp_hire_and_sep_info(self, emp):
        """Extracts hire_date, sep_date, is_voluntary, and is_critical_role safely across Odoo 19 hr.employee & hr.version."""
        hire_date = (
            getattr(emp, "contract_date_start", False)
            or getattr(emp, "first_contract_date", False)
            or (getattr(emp, "version_id", False) and getattr(emp.version_id, "contract_date_start", False))
            or (getattr(emp, "contract_id", False) and getattr(emp.contract_id, "date_start", False))
        )
        if not hire_date and getattr(emp, "create_date", False):
            hire_date = emp.create_date.date() if isinstance(emp.create_date, datetime) else emp.create_date

        sep_date = (
            getattr(emp, "departure_date", False)
            or (not emp.active and getattr(emp, "contract_date_end", False))
            or (
                getattr(emp, "version_id", False)
                and not emp.active
                and getattr(emp.version_id, "contract_date_end", False)
            )
            or (
                getattr(emp, "contract_id", False)
                and not emp.active
                and getattr(emp.contract_id, "date_end", False)
            )
        )
        # Also check contract_date_end if employment status/departure reason is set
        if not sep_date and getattr(emp, "departure_reason_id", False):
            sep_date = (
                getattr(emp, "contract_date_end", False)
                or (getattr(emp, "version_id", False) and getattr(emp.version_id, "contract_date_end", False))
            )

        dep_reason = ((getattr(emp, "departure_reason_id", False) and emp.departure_reason_id.name) or "").lower()
        is_voluntary = True
        if dep_reason and any(k in dep_reason for k in ["fired", "dismiss", "فصل", "انهاء", "إنهاء", "retire", "تقاعد", "end of contract"]):
            if "resign" not in dep_reason and "استقال" not in dep_reason:
                is_voluntary = False

        job_name = (
            ((getattr(emp, "job_id", False) and emp.job_id.name) or getattr(emp, "job_title", "") or "")
        ).lower()
        wage = (
            getattr(emp, "wage", 0.0)
            or (getattr(emp, "version_id", False) and getattr(emp.version_id, "wage", 0.0))
            or (getattr(emp, "contract_id", False) and getattr(emp.contract_id, "wage", 0.0))
            or 0.0
        )
        is_critical = bool(
            wage >= 600.0
            or any(
                k in job_name
                for k in [
                    "manager",
                    "director",
                    "head",
                    "supervisor",
                    "chief",
                    "lead",
                    "specialist",
                    "engineer",
                    "مدير",
                    "رئيس",
                    "مشرف",
                    "مسؤول",
                    "شيف",
                    "مهندس",
                    "محاسب رئيسي",
                ]
            )
        )
        return {
            "hire_date": hire_date,
            "sep_date": sep_date,
            "is_voluntary": is_voluntary,
            "is_critical": is_critical,
            "wage": float(wage or 0.0),
        }

    @api.model
    def _summarize_period_slips(self, p_start, p_end, target_company_id, user_companies, all_target_dep_ids_set, preloaded_slips=None):
        """Fast helper to summarize a month's payslip costs (Basic, Allowances, OT, Health Ins, Co. SS, EOS, Total Cost)."""
        if preloaded_slips is not None:
            slips = preloaded_slips
        else:
            dom = [
                ("state", "not in", ["cancel"]),
                ("date_from", "<=", p_end),
                ("date_to", ">=", p_start),
            ]
            if target_company_id > 0:
                dom.append(("company_id", "=", target_company_id))
            else:
                dom.append(("company_id", "in", user_companies.ids))

            if all_target_dep_ids_set:
                t_list = list(all_target_dep_ids_set)
                dom.extend(["|", ("employee_id.department_id", "in", t_list), ("department_id", "in", t_list)])

            slips = self.env["hr.payslip"].sudo().search(dom)
            if all_target_dep_ids_set:
                slips = slips.filtered(
                    lambda s: (
                        ((s.employee_id and s.employee_id.department_id) or s.department_id).id in all_target_dep_ids_set
                    )
                    if ((s.employee_id and s.employee_id.department_id) or s.department_id)
                    else False
                )

        if slips:
            try:
                slips.mapped("line_ids")
            except Exception:
                pass

        sbu_defs = [
            ("united", "شركة الوحدة", "United Company"),
            ("delta_factory", "شركة دلتا (المصنع)", "Delta Factory"),
            ("admin", "الادارة", "Administration (HO)"),
            ("retail_amman", "Retail Amman", "Retail Amman"),
            ("retail_alhadaf", "Retail Alhadaf", "Retail Alhadaf (Aqaba)"),
        ]
        sbu_buckets = {
            k: {
                "sbu_key": k,
                "sbu_name_ar": ar,
                "sbu_name_en": en,
                "sbu_display_name": f"{ar} ({en})" if ar != en else ar,
                "basic_salary": 0.0,
                "allowances": 0.0,
                "overtime_amount": 0.0,
                "health_ins_comp": 0.0,
                "social_security_comp": 0.0,
                "eos_amount": 0.0,
                "other_adjustments": 0.0,
                "total_workforce_cost": 0.0,
                "underlying_workforce_cost": 0.0,
                "slip_emp_ids": set(),
                "term_emp_ids": set(),
            }
            for k, ar, en in sbu_defs
        }

        tot_basic = 0.0
        tot_alw = 0.0
        tot_ot = 0.0
        tot_med = 0.0
        tot_ssc = 0.0
        tot_eos = 0.0
        eos_slips_cnt = 0

        for slip in slips:
            emp = slip.employee_id
            dep = (emp and emp.department_id) or slip.department_id
            comp = (emp and emp.company_id) or slip.company_id
            sbu_k = self._classify_sbu_key(emp=emp, dep=dep, comp=comp)
            bkt = sbu_buckets[sbu_k]
            if emp:
                bkt["slip_emp_ids"].add(emp.id)

            struct_name_low = ((slip.struct_id and slip.struct_id.name) or "").lower()
            is_term_slip = (
                "termination" in struct_name_low
                or "مخالصة" in struct_name_low
                or bool(getattr(slip, "is_termination", False))
            )
            if is_term_slip and emp:
                bkt["term_emp_ids"].add(emp.id)

            c_wage = (
                (emp and getattr(emp, "wage", 0.0))
                or getattr(slip, "basic_wage", 0.0)
                or getattr(slip, "wage", 0.0)
                or 0.0
            )
            s_basic = 0.0
            s_alw = 0.0
            s_ot = 0.0
            s_ssc_emp = 0.0
            s_ssc_comp = 0.0
            s_med_comp = 0.0
            s_has_med = False
            s_eos = 0.0

            for line in getattr(slip, "line_ids", []):
                code = (line.code or "").upper().strip()
                cat_code = (line.category_id.code or "").upper().strip() if line.category_id else ""
                name = (line.name or "").lower().strip()
                amt = line.total or 0.0

                if code in ("NET", "GROSS", "GRS", "TOTAL_GROSS") or cat_code in ("NET", "GROSS"):
                    continue
                is_actual = code in ("FULL_WAGE", "ACTUAL_SALARY", "ACTUAL") or "actual salary" in name or "الراتب الفعلي" in name
                if is_actual:
                    continue
                if code in ("BASIC", "SALARY", "BASE", "WAGE") or cat_code == "BASIC":
                    s_basic += amt
                    continue

                is_ot = (
                    code in ("OT_NET", "ETH_NET", "RD-S", "OVERTIME", "GROSS_ATT", "OT_COMP", "EXTRA_HOURS", "TERM_EXTRA", "OT")
                    or any(k in code for k in ["OT", "OVERTIME", "EXTRA"])
                    or any(k in name for k in ["اضافي", "إضافي", "عمل إضافي", "عمل اضافي", "extra hours"])
                )
                if is_ot and cat_code not in ("DED", "DEDUCTION"):
                    s_ot += amt
                    continue

                is_eos = (
                    code in ("EOS", "EOSB", "END_OF_SERVICE", "INDEMNITY", "TERM_PTO", "TERM_ANNUAL", "CLEAR_ANNUAL", "CLEAR_PTO")
                    or any(k in code for k in ["EOS", "INDEMNITY", "TERM_"])
                    or any(k in name for k in ["نهاية الخدمة", "نهاية خدمة", "مخالصة", "termination", "end of service"])
                )
                if is_eos and cat_code not in ("DED", "DEDUCTION"):
                    s_eos += abs(amt)
                    continue

                is_med_c = code in ("MED_COMP", "INS_COMP", "HEALTH_COMP") or ("تأمين صحي" in name and ("شركة" in name or "صاحب العمل" in name))
                if is_med_c:
                    s_med_comp += abs(amt)
                    continue

                if code == "INS" or "تأمين صحي" in name or "تامين صحي" in name:
                    if abs(amt) > 0:
                        s_has_med = True

                is_ss_emp = code in ("SSE", "SSCE", "SSC_EMP", "SOC_SEC_EMP") or ("ضمان" in name and "موظف" in name)
                is_ss_comp = code in ("SSC", "SSCC", "SSC_COMP", "SOC_SEC_COMP") or ("ضمان" in name and ("شركة" in name or "صاحب العمل" in name))
                is_ss_gen = any(k in code for k in ["SS", "SSC", "GOSI"]) or "ضمان" in name
                if is_ss_emp or is_ss_comp or is_ss_gen:
                    if is_ss_comp or any(k in code for k in ["COMP", "COMPANY", "ER", "SSCCO", "SSCP"]):
                        s_ssc_comp += abs(amt)
                    else:
                        s_ssc_emp += abs(amt)
                    continue

                is_alw = (
                    cat_code in ("ALW", "ALLOWANCE", "ALW_RECURRING")
                    or code in ("ALW", "BONUS", "COMMISSION", "ALLW", "TAKLEEF", "TAKLEF", "TRANS", "HOUSING")
                    or any(k in name for k in ["علاوة", "مكافأة", "مكافاه", "بدل", "تكليف", "تنقل"])
                )
                if is_alw:
                    s_alw += amt

            if not s_basic:
                s_basic = c_wage
            if not s_med_comp and s_has_med:
                s_med_comp = 13.0
            # Employer Social Security Share (14.25% in Jordan = 1.9 * 7.5% employee share if SSC line not explicitly on slip)
            if not s_ssc_comp and s_ssc_emp > 0:
                s_ssc_comp = round(s_ssc_emp * (14.25 / 7.5), 3)

            if is_term_slip:
                eos_slips_cnt += 1
                if not s_eos:
                    s_eos = max(s_alw + s_ot, 0.0)
                    s_alw = 0.0
                    s_ot = 0.0
            elif s_eos > 0:
                eos_slips_cnt += 1

            bkt["basic_salary"] += s_basic
            bkt["allowances"] += s_alw
            bkt["overtime_amount"] += s_ot
            bkt["health_ins_comp"] += s_med_comp
            bkt["social_security_comp"] += s_ssc_comp
            bkt["eos_amount"] += s_eos

            tot_basic += s_basic
            tot_alw += s_alw
            tot_ot += s_ot
            tot_med += s_med_comp
            tot_ssc += s_ssc_comp
            tot_eos += s_eos

        tot_wf_cost = tot_basic + tot_alw + tot_ot + tot_med + tot_ssc + tot_eos
        tot_underlying_cost = tot_wf_cost - tot_eos

        for bkt in sbu_buckets.values():
            bkt["total_workforce_cost"] = round(
                bkt["basic_salary"]
                + bkt["allowances"]
                + bkt["overtime_amount"]
                + bkt["health_ins_comp"]
                + bkt["social_security_comp"]
                + bkt["eos_amount"]
                + bkt["other_adjustments"],
                3,
            )
            bkt["underlying_workforce_cost"] = round(bkt["total_workforce_cost"] - bkt["eos_amount"], 3)

        return {
            "sbu_buckets": sbu_buckets,
            "basic_salary": round(tot_basic, 3),
            "allowances": round(tot_alw, 3),
            "overtime_amount": round(tot_ot, 3),
            "health_ins_comp": round(tot_med, 3),
            "social_security_comp": round(tot_ssc, 3),
            "eos_amount": round(tot_eos, 3),
            "total_workforce_cost": round(tot_wf_cost, 3),
            "underlying_workforce_cost": round(tot_underlying_cost, 3),
            "eos_slip_count": eos_slips_cnt,
            "slip_emp_count": len(set().union(*(b["slip_emp_ids"] for b in sbu_buckets.values()))),
        }

    @api.model
    def _compute_workforce_and_labor_cost_analytics(
        self,
        start_date,
        end_date,
        target_company_id,
        user_companies,
        all_target_dep_ids_set,
        current_payslips,
        filtered_active_emps,
        total_basic_salary,
        total_allowances,
        total_overtime_amount,
        total_social_security_emp,
        total_social_security_comp,
        total_health_ins_comp,
        total_eos_amount,
        eos_slip_count,
        effective_kpi_headcount,
    ):
        """
        Computes:
          1. `labor_cost_report` & `labor_cost_totals` (Exact 15-col `Employee Cost.xlsx` model)
          2. `cost_bridge` (Slide 4: Headline Workforce Cost vs EOS vs Underlying Cost)
          3. `workforce_movement` (Slides 2, 3, 7, 8, 9: Beginning HC, Hires, Separations, Ending HC, Voluntary %, Critical Exits)
          4. `three_month_trend` (Slides 1, 5, 7, 10: Month-2, Month-1, Current Month + MoM % + RAG)
          5. `executive_insights` (Slides 6 & 8: Auto-generated Positives, Attention Points, Priorities)
        """
        # Fetch all employees (active + archived) in company/department filter scope for accurate historical movement
        emp_dom = [("company_id", "=", target_company_id)] if target_company_id > 0 else [("company_id", "in", user_companies.ids)]
        if all_target_dep_ids_set:
            emp_dom.append(("department_id", "in", list(all_target_dep_ids_set)))
        all_emps_with_archived = self.env["hr.employee"].with_context(active_test=False).sudo().search(emp_dom)

        emp_records_meta = []
        for e in all_emps_with_archived:
            info = self._get_emp_hire_and_sep_info(e)
            sbu_k = self._classify_sbu_key(emp=e, dep=e.department_id, comp=e.company_id)
            emp_records_meta.append({
                "id": e.id,
                "active": e.active,
                "sbu_key": sbu_k,
                "hire_date": info["hire_date"],
                "sep_date": info["sep_date"],
                "is_voluntary": info["is_voluntary"],
                "is_critical": info["is_critical"],
            })

        def _compute_hc_movement_for_window(w_start, w_end, term_emp_ids_by_sbu=None):
            sbu_keys = ["united", "delta_factory", "admin", "retail_amman", "retail_alhadaf"]
            m_by_sbu = {
                k: {
                    "beginning_hc": 0,
                    "new_hires": 0,
                    "separations": 0,
                    "ending_hc": 0,
                    "net_movement": 0,
                    "voluntary_separations": 0,
                    "critical_departures": 0,
                }
                for k in sbu_keys
            }
            for em in emp_records_meta:
                sk = em["sbu_key"]
                h_dt = em["hire_date"]
                s_dt = em["sep_date"]
                in_term_slips = bool(term_emp_ids_by_sbu and em["id"] in term_emp_ids_by_sbu.get(sk, set()))

                # Active at start of window: hired before w_start and not separated before w_start
                hired_before = (not h_dt) or (h_dt < w_start)
                not_left_before = (not s_dt and em["active"]) or (s_dt and s_dt >= w_start)
                if hired_before and not_left_before:
                    m_by_sbu[sk]["beginning_hc"] += 1

                # Hired during window
                if h_dt and (w_start <= h_dt <= w_end):
                    m_by_sbu[sk]["new_hires"] += 1

                # Separated during window (either departure_date in window or termination slip in window)
                left_in_window = (s_dt and (w_start <= s_dt <= w_end)) or (not s_dt and in_term_slips)
                if left_in_window:
                    m_by_sbu[sk]["separations"] += 1
                    if em["is_voluntary"]:
                        m_by_sbu[sk]["voluntary_separations"] += 1
                    if em["is_critical"]:
                        m_by_sbu[sk]["critical_departures"] += 1

            for sk, mv in m_by_sbu.items():
                mv["ending_hc"] = max(mv["beginning_hc"] + mv["new_hires"] - mv["separations"], 0)
                mv["net_movement"] = mv["new_hires"] - mv["separations"]
            return m_by_sbu

        # Determine the 3 rolling monthly windows: M-2, M-1, M0 (Current)
        m0_start = start_date.replace(day=1)
        m0_next = (m0_start + timedelta(days=32)).replace(day=1)
        m0_end = end_date if (end_date - start_date).days >= 20 else (m0_next - timedelta(days=1))

        m1_end = m0_start - timedelta(days=1)
        m1_start = m1_end.replace(day=1)

        m2_end = m1_start - timedelta(days=1)
        m2_start = m2_end.replace(day=1)

        # Summarize payslips for M0 (using current_payslips), M-1, M-2
        m0_summary = self._summarize_period_slips(start_date, end_date, target_company_id, user_companies, all_target_dep_ids_set, preloaded_slips=current_payslips)
        m1_summary = self._summarize_period_slips(m1_start, m1_end, target_company_id, user_companies, all_target_dep_ids_set)
        m2_summary = self._summarize_period_slips(m2_start, m2_end, target_company_id, user_companies, all_target_dep_ids_set)

        m0_term_by_sbu = {k: b["term_emp_ids"] for k, b in m0_summary["sbu_buckets"].items()}
        m1_term_by_sbu = {k: b["term_emp_ids"] for k, b in m1_summary["sbu_buckets"].items()}
        m2_term_by_sbu = {k: b["term_emp_ids"] for k, b in m2_summary["sbu_buckets"].items()}

        m0_hc_sbu = _compute_hc_movement_for_window(start_date, end_date, m0_term_by_sbu)
        m1_hc_sbu = _compute_hc_movement_for_window(m1_start, m1_end, m1_term_by_sbu)
        m2_hc_sbu = _compute_hc_movement_for_window(m2_start, m2_end, m2_term_by_sbu)

        # Build the 5 SBU rows for `labor_cost_report` (Matching `Employee Cost.xlsx` Sheet 1)
        sbu_order = ["united", "delta_factory", "admin", "retail_amman", "retail_alhadaf"]
        labor_cost_report = []

        tot_beg_hc = 0
        tot_hires = 0
        tot_seps = 0
        tot_end_hc = 0
        tot_vol_seps = 0
        tot_crit_seps = 0

        for sk in sbu_order:
            bkt = m0_summary["sbu_buckets"][sk]
            mv = m0_hc_sbu[sk]
            beg_hc = mv["beginning_hc"]
            hires = mv["new_hires"]
            seps = mv["separations"]
            end_hc = mv["ending_hc"]
            if end_hc == 0 and len(bkt["slip_emp_ids"]) > 0:
                end_hc = len(bkt["slip_emp_ids"])
                beg_hc = max(end_hc - hires + seps, 0)

            net_mv = hires - seps
            wf_cost = bkt["total_workforce_cost"]
            eos_cost = bkt["eos_amount"]
            und_cost = bkt["underlying_workforce_cost"]
            avg_und_cost = round(und_cost / end_hc, 3) if end_hc > 0 else 0.0
            ot_pct = round((bkt["overtime_amount"] / wf_cost * 100.0), 2) if wf_cost > 0 else 0.0
            turnover_pct = round((seps / beg_hc * 100.0), 2) if beg_hc > 0 else 0.0
            vol_share_pct = round((mv["voluntary_separations"] / seps * 100.0), 1) if seps > 0 else 0.0

            if turnover_pct >= 5.0 or mv["critical_departures"] >= 2 or net_mv <= -5:
                rag_status = "critical"
                rag_label = "Critical Risk"
            elif turnover_pct >= 2.5 or seps > 0 or net_mv < 0:
                rag_status = "monitor"
                rag_label = "Monitor"
            else:
                rag_status = "optimal"
                rag_label = "Optimal / Stable"

            labor_cost_report.append({
                "sbu_key": sk,
                "sbu_name_ar": bkt["sbu_name_ar"],
                "sbu_name_en": bkt["sbu_name_en"],
                "sbu_display_name": bkt["sbu_display_name"],
                "beginning_hc": beg_hc,
                "new_hires": hires,
                "separations": seps,
                "ending_hc": end_hc,
                "net_movement": net_mv,
                "basic_salary": round(bkt["basic_salary"], 3),
                "allowances": round(bkt["allowances"], 3),
                "overtime_amount": round(bkt["overtime_amount"], 3),
                "health_ins_comp": round(bkt["health_ins_comp"], 3),
                "social_security_comp": round(bkt["social_security_comp"], 3),
                "eos_amount": round(eos_cost, 3),
                "other_adjustments": round(bkt["other_adjustments"], 3),
                "total_workforce_cost": round(wf_cost, 3),
                "underlying_workforce_cost": round(und_cost, 3),
                "underlying_avg_cost_per_emp": avg_und_cost,
                "overtime_cost_pct": ot_pct,
                "turnover_rate": turnover_pct,
                "voluntary_separations": mv["voluntary_separations"],
                "voluntary_share_pct": vol_share_pct,
                "critical_departures": mv["critical_departures"],
                "rag_status": rag_status,
                "rag_label": rag_label,
            })

            tot_beg_hc += beg_hc
            tot_hires += hires
            tot_seps += seps
            tot_end_hc += end_hc
            tot_vol_seps += mv["voluntary_separations"]
            tot_crit_seps += mv["critical_departures"]

        if tot_end_hc == 0 and effective_kpi_headcount > 0:
            tot_end_hc = effective_kpi_headcount
            tot_beg_hc = max(tot_end_hc - tot_hires + tot_seps, 0)

        tot_wf_cost = m0_summary["total_workforce_cost"]
        tot_eos_cost = m0_summary["eos_amount"]
        tot_und_cost = m0_summary["underlying_workforce_cost"]
        tot_avg_und = round(tot_und_cost / tot_end_hc, 3) if tot_end_hc > 0 else 0.0
        tot_ot_pct = round((m0_summary["overtime_amount"] / tot_wf_cost * 100.0), 2) if tot_wf_cost > 0 else 0.0
        tot_turnover_pct = round((tot_seps / tot_beg_hc * 100.0), 2) if tot_beg_hc > 0 else 0.0
        tot_vol_share_pct = round((tot_vol_seps / tot_seps * 100.0), 1) if tot_seps > 0 else 0.0

        labor_cost_totals = {
            "sbu_name_ar": "الإجمالي الكلي",
            "sbu_display_name": "الإجمالي (Grand Total)",
            "beginning_hc": tot_beg_hc,
            "new_hires": tot_hires,
            "separations": tot_seps,
            "ending_hc": tot_end_hc,
            "net_movement": tot_hires - tot_seps,
            "basic_salary": m0_summary["basic_salary"],
            "allowances": m0_summary["allowances"],
            "overtime_amount": m0_summary["overtime_amount"],
            "health_ins_comp": m0_summary["health_ins_comp"],
            "social_security_comp": m0_summary["social_security_comp"],
            "eos_amount": tot_eos_cost,
            "other_adjustments": 0.0,
            "total_workforce_cost": tot_wf_cost,
            "underlying_workforce_cost": tot_und_cost,
            "underlying_avg_cost_per_emp": tot_avg_und,
            "overtime_cost_pct": tot_ot_pct,
            "turnover_rate": tot_turnover_pct,
            "voluntary_separations": tot_vol_seps,
            "voluntary_share_pct": tot_vol_share_pct,
            "critical_departures": tot_crit_seps,
        }

        # Aggregate M-1 and M-2 headcount totals for the 3-Month Trend table
        def _agg_hc_window(hc_sbu_map, slip_summary):
            b_hc = sum(v["beginning_hc"] for v in hc_sbu_map.values())
            n_hr = sum(v["new_hires"] for v in hc_sbu_map.values())
            s_ep = sum(v["separations"] for v in hc_sbu_map.values())
            e_hc = sum(v["ending_hc"] for v in hc_sbu_map.values())
            if e_hc == 0 and slip_summary["slip_emp_count"] > 0:
                e_hc = slip_summary["slip_emp_count"]
                b_hc = max(e_hc - n_hr + s_ep, 0)
            v_sep = sum(v["voluntary_separations"] for v in hc_sbu_map.values())
            c_dep = sum(v["critical_departures"] for v in hc_sbu_map.values())
            t_rate = round((s_ep / b_hc * 100.0), 2) if b_hc > 0 else 0.0
            v_share = round((v_sep / s_ep * 100.0), 1) if s_ep > 0 else 0.0
            avg_und = round(slip_summary["underlying_workforce_cost"] / e_hc, 2) if e_hc > 0 else 0.0
            return {
                "beginning_hc": b_hc,
                "new_hires": n_hr,
                "separations": s_ep,
                "ending_hc": e_hc,
                "net_movement": n_hr - s_ep,
                "turnover_rate": t_rate,
                "voluntary_share_pct": v_share,
                "critical_departures": c_dep,
                "avg_underlying_cost": avg_und,
            }

        m1_agg = _agg_hc_window(m1_hc_sbu, m1_summary)
        m2_agg = _agg_hc_window(m2_hc_sbu, m2_summary)

        # Headline vs Underlying Cost Bridge (Slide 4)
        avg_mom_pct = (
            round(((tot_avg_und - m1_agg["avg_underlying_cost"]) / m1_agg["avg_underlying_cost"]) * 100.0, 1)
            if m1_agg["avg_underlying_cost"] > 0
            else 0.0
        )
        cost_bridge = {
            "reported_workforce_cost": tot_wf_cost,
            "eos_settlement_cost": tot_eos_cost,
            "underlying_workforce_cost": tot_und_cost,
            "reported_avg_cost_per_emp": round(tot_wf_cost / tot_end_hc, 3) if tot_end_hc > 0 else 0.0,
            "underlying_avg_cost_per_emp": tot_avg_und,
            "prev_underlying_avg_cost_per_emp": m1_agg["avg_underlying_cost"],
            "avg_cost_mom_pct": avg_mom_pct,
            "eos_slip_count": m0_summary["eos_slip_count"],
            "eos_pct_of_reported": round((tot_eos_cost / tot_wf_cost * 100.0), 1) if tot_wf_cost > 0 else 0.0,
        }

        # 3-Month Rolling Trend Table (Slide 1, 5, 7, 10)
        def _mom_badge(curr_v, prev_v, lower_is_better=False, is_pct_points=False):
            diff = curr_v - prev_v
            if is_pct_points:
                txt = f"{'+' if diff >= 0 else ''}{round(diff, 2)} pp"
            elif prev_v:
                pct = round((diff / abs(prev_v)) * 100.0, 1)
                txt = f"{'+' if pct >= 0 else ''}{pct}%"
            else:
                txt = f"{'+' if diff >= 0 else ''}{round(diff, 1)}"

            if abs(diff) < 0.01:
                rag = "amber"
            elif lower_is_better:
                rag = "green" if diff < 0 else "red"
            else:
                rag = "green" if diff > 0 else "red"
            return txt, rag

        hc_mom_txt, hc_rag = _mom_badge(tot_end_hc, m1_agg["ending_hc"], lower_is_better=False)
        hires_mom_txt, hires_rag = _mom_badge(tot_hires, m1_agg["new_hires"], lower_is_better=False)
        seps_mom_txt, seps_rag = _mom_badge(tot_seps, m1_agg["separations"], lower_is_better=True)
        net_mv_curr = tot_hires - tot_seps
        net_mv_prev = m1_agg["net_movement"]
        net_mom_txt = "Improving" if net_mv_curr > net_mv_prev else ("Stable" if net_mv_curr == net_mv_prev else "Workforce Contraction")
        net_rag = "green" if net_mv_curr >= 0 else ("amber" if net_mv_curr > net_mv_prev else "red")

        avg_c_mom_txt, avg_c_rag = _mom_badge(tot_avg_und, m1_agg["avg_underlying_cost"], lower_is_better=True)
        ot_mom_txt, ot_rag = _mom_badge(m0_summary["overtime_amount"], m1_summary["overtime_amount"], lower_is_better=True)
        und_mom_txt, und_rag = _mom_badge(tot_und_cost, m1_summary["underlying_workforce_cost"], lower_is_better=True)
        turn_mom_txt, turn_rag = _mom_badge(tot_turnover_pct, m1_agg["turnover_rate"], lower_is_better=True, is_pct_points=True)
        vol_mom_txt, vol_rag = _mom_badge(tot_vol_share_pct, m1_agg["voluntary_share_pct"], lower_is_better=True, is_pct_points=True)
        crit_mom_txt, crit_rag = _mom_badge(tot_crit_seps, m1_agg["critical_departures"], lower_is_better=True)

        m2_rep_avg = round(m2_summary["total_workforce_cost"] / m2_agg["ending_hc"], 2) if m2_agg["ending_hc"] > 0 else 0.0
        m1_rep_avg = round(m1_summary["total_workforce_cost"] / m1_agg["ending_hc"], 2) if m1_agg["ending_hc"] > 0 else 0.0
        m0_rep_avg = round(tot_wf_cost / tot_end_hc, 2) if tot_end_hc > 0 else 0.0
        m2_ot_pct = round((m2_summary["overtime_amount"] / m2_summary["total_workforce_cost"] * 100.0), 2) if m2_summary["total_workforce_cost"] > 0 else 0.0
        m1_ot_pct = round((m1_summary["overtime_amount"] / m1_summary["total_workforce_cost"] * 100.0), 2) if m1_summary["total_workforce_cost"] > 0 else 0.0

        three_month_trend = {
            "m2_label": m2_start.strftime("%b %Y"),
            "m1_label": m1_start.strftime("%b %Y"),
            "m0_label": m0_start.strftime("%b %Y"),
            "series_3m": {
                "beg_hc": [m2_agg["beginning_hc"], m1_agg["beginning_hc"], tot_beg_hc],
                "end_hc": [m2_agg["ending_hc"], m1_agg["ending_hc"], tot_end_hc],
                "hires": [m2_agg["new_hires"], m1_agg["new_hires"], tot_hires],
                "seps": [m2_agg["separations"], m1_agg["separations"], tot_seps],
                "rep_cost": [m2_summary["total_workforce_cost"], m1_summary["total_workforce_cost"], tot_wf_cost],
                "eos_cost": [m2_summary["eos_amount"], m1_summary["eos_amount"], tot_eos_cost],
                "und_cost": [m2_summary["underlying_workforce_cost"], m1_summary["underlying_workforce_cost"], tot_und_cost],
                "rep_avg": [m2_rep_avg, m1_rep_avg, m0_rep_avg],
                "und_avg": [m2_agg["avg_underlying_cost"], m1_agg["avg_underlying_cost"], tot_avg_und],
                "ot_cost": [m2_summary["overtime_amount"], m1_summary["overtime_amount"], m0_summary["overtime_amount"]],
                "ot_pct": [m2_ot_pct, m1_ot_pct, tot_ot_pct],
            },
            "rows": [
                {
                    "kpi": "Ending Headcount (عدد الموظفين نهاية الشهر)",
                    "m2": f"{m2_agg['ending_hc']}",
                    "m1": f"{m1_agg['ending_hc']}",
                    "m0": f"{tot_end_hc}",
                    "mom": hc_mom_txt,
                    "rag": hc_rag,
                },
                {
                    "kpi": "New Hires (تعيينات جديدة)",
                    "m2": f"{m2_agg['new_hires']}",
                    "m1": f"{m1_agg['new_hires']}",
                    "m0": f"{tot_hires}",
                    "mom": hires_mom_txt,
                    "rag": hires_rag,
                },
                {
                    "kpi": "Separations / Exits (إنهاء خدمات / مغادرين)",
                    "m2": f"{m2_agg['separations']}",
                    "m1": f"{m1_agg['separations']}",
                    "m0": f"{tot_seps}",
                    "mom": seps_mom_txt,
                    "rag": seps_rag,
                },
                {
                    "kpi": "Net Workforce Movement (صافي حركة الكادر)",
                    "m2": f"{'+' if m2_agg['net_movement'] > 0 else ''}{m2_agg['net_movement']}",
                    "m1": f"{'+' if m1_agg['net_movement'] > 0 else ''}{m1_agg['net_movement']}",
                    "m0": f"{'+' if net_mv_curr > 0 else ''}{net_mv_curr}",
                    "mom": net_mom_txt,
                    "rag": net_rag,
                },
                {
                    "kpi": "Reported Workforce Cost (إجمالي التكلفة شامل المخالصات)",
                    "m2": f"{m2_summary['total_workforce_cost']:,.1f} JOD",
                    "m1": f"{m1_summary['total_workforce_cost']:,.1f} JOD",
                    "m0": f"{tot_wf_cost:,.1f} JOD",
                    "mom": _mom_badge(tot_wf_cost, m1_summary["total_workforce_cost"], lower_is_better=True)[0],
                    "rag": _mom_badge(tot_wf_cost, m1_summary["total_workforce_cost"], lower_is_better=True)[1],
                },
                {
                    "kpi": "End-of-Service / EOS Settlements (مستحقات نهاية الخدمة)",
                    "m2": f"{m2_summary['eos_amount']:,.1f} JOD",
                    "m1": f"{m1_summary['eos_amount']:,.1f} JOD",
                    "m0": f"{tot_eos_cost:,.1f} JOD",
                    "mom": f"{m0_summary['eos_slip_count']} Slips",
                    "rag": "amber" if tot_eos_cost > 0 else "green",
                },
                {
                    "kpi": "Underlying Workforce Cost Excl. EOS (التكلفة التشغيلية بدون EOS)",
                    "m2": f"{m2_summary['underlying_workforce_cost']:,.1f} JOD",
                    "m1": f"{m1_summary['underlying_workforce_cost']:,.1f} JOD",
                    "m0": f"{tot_und_cost:,.1f} JOD",
                    "mom": und_mom_txt,
                    "rag": und_rag,
                },
                {
                    "kpi": "Avg. Cost / Employee Excl. EOS (متوسط تكلفة الموظف التشغيلي)",
                    "m2": f"{m2_agg['avg_underlying_cost']:,.1f} JOD",
                    "m1": f"{m1_agg['avg_underlying_cost']:,.1f} JOD",
                    "m0": f"{tot_avg_und:,.1f} JOD",
                    "mom": avg_c_mom_txt,
                    "rag": avg_c_rag,
                },
                {
                    "kpi": "Overtime Cost (تكلفة العمل الإضافي)",
                    "m2": f"{m2_summary['overtime_amount']:,.1f} JOD",
                    "m1": f"{m1_summary['overtime_amount']:,.1f} JOD",
                    "m0": f"{m0_summary['overtime_amount']:,.1f} JOD",
                    "mom": ot_mom_txt,
                    "rag": ot_rag,
                },
                {
                    "kpi": "Overall Turnover Rate (نسبة الدوران الوظيفي)",
                    "m2": f"{m2_agg['turnover_rate']}%",
                    "m1": f"{m1_agg['turnover_rate']}%",
                    "m0": f"{tot_turnover_pct}%",
                    "mom": turn_mom_txt,
                    "rag": turn_rag,
                },
                {
                    "kpi": "Voluntary Turnover Share (نسبة الاستقالات الطوعية)",
                    "m2": f"{m2_agg['voluntary_share_pct']}%",
                    "m1": f"{m1_agg['voluntary_share_pct']}%",
                    "m0": f"{tot_vol_share_pct}%",
                    "mom": vol_mom_txt,
                    "rag": vol_rag,
                },
                {
                    "kpi": "Critical Role Departures (مغادرة الكفاءات الحرجة)",
                    "m2": f"{m2_agg['critical_departures']}",
                    "m1": f"{m1_agg['critical_departures']}",
                    "m0": f"{tot_crit_seps}",
                    "mom": crit_mom_txt,
                    "rag": crit_rag,
                },
            ],
        }

        # Auto-Generated Executive Insights (Slide 6 & Slide 8)
        positives = []
        attention_points = []
        priorities = [
            "Validate workforce capacity requirements in Delta Factory and Retail branches.",
            "Analyze monthly separations, focusing on voluntary resignations and critical-role exits.",
            "Track Underlying Workforce Cost (excluding EOS settlements) separately for accurate month-over-month comparability.",
            "Monitor Retail overtime by branch, shift, and attendance logs.",
        ]

        if m0_summary["overtime_amount"] <= m1_summary["overtime_amount"] and m1_summary["overtime_amount"] > 0:
            positives.append(f"Overtime cost controlled at {m0_summary['overtime_amount']:,.1f} JOD ({ot_mom_txt} vs previous month).")
        else:
            positives.append(f"Active workforce of {tot_end_hc} staff tracked across all 5 Strategic Business Units.")

        if tot_avg_und <= m1_agg["avg_underlying_cost"] or m1_agg["avg_underlying_cost"] == 0:
            positives.append(f"Underlying average employee cost remains controlled at {tot_avg_und:,.1f} JOD/employee (excluding EOS).")
        if tot_eos_cost > 0:
            positives.append(f"Isolated {tot_eos_cost:,.1f} JOD of one-time End-of-Service (EOS) settlements from recurring operating cost.")

        retail_ot = (
            m0_summary["sbu_buckets"]["retail_amman"]["overtime_amount"]
            + m0_summary["sbu_buckets"]["retail_alhadaf"]["overtime_amount"]
        )
        retail_ot_share = round((retail_ot / m0_summary["overtime_amount"] * 100.0), 1) if m0_summary["overtime_amount"] > 0 else 0.0
        if retail_ot_share >= 50.0:
            attention_points.append(f"Retail (Amman + Alhadaf) accounts for {retail_ot_share}% ({retail_ot:,.1f} JOD) of total corporate overtime.")
        if net_mv_curr < 0:
            attention_points.append(f"Net workforce contracted by {abs(net_mv_curr)} employees ({tot_hires} hires vs {tot_seps} separations).")
        if tot_seps > 0:
            attention_points.append(f"Total of {tot_seps} separations recorded ({tot_vol_share_pct}% voluntary resignations, {tot_crit_seps} critical-role exits).")
        if not attention_points:
            attention_points.append("Continue monitoring branch-level labor cost ratios and overtime utilization.")

        return {
            "labor_cost_report": labor_cost_report,
            "labor_cost_totals": labor_cost_totals,
            "cost_bridge": cost_bridge,
            "three_month_trend": three_month_trend,
            "workforce_movement": {
                "beginning_hc": tot_beg_hc,
                "new_hires": tot_hires,
                "separations": tot_seps,
                "ending_hc": tot_end_hc,
                "net_movement": net_mv_curr,
                "turnover_rate": tot_turnover_pct,
                "voluntary_separations": tot_vol_seps,
                "voluntary_share_pct": tot_vol_share_pct,
                "critical_departures": tot_crit_seps,
            },
            "executive_insights": {
                "positives": positives,
                "attention_points": attention_points,
                "priorities": priorities,
            },
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
