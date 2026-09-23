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

        # Base Domain for Payslips (Includes ALL validated payslips: bulk & separate)
        slip_domain = [
            ("state", "not in", ["cancel"]),
            ("date_from", "<=", end_date),
            ("date_to", ">=", start_date),
        ]
        target_payrun_id = int(payrun_id) if payrun_id and int(payrun_id) > 0 else 0
        if target_payrun_id > 0:
            slip_domain.append(("payslip_run_id", "=", target_payrun_id))

        if target_company_id > 0:
            slip_domain.append(("company_id", "=", target_company_id))
        else:
            slip_domain.append(("company_id", "in", user_companies.ids))

        # Resolve selected departments and all their child departments (hierarchical)
        if department_ids:
            raw_dep_ids = [int(d) for d in department_ids if int(d) > 0]
            if raw_dep_ids:
                all_target_dep_ids = self.env["hr.department"].search([("id", "child_of", raw_dep_ids)]).ids
                slip_domain.extend([
                    "|",
                    ("department_id", "in", all_target_dep_ids),
                    ("employee_id.department_id", "in", all_target_dep_ids),
                ])

        payslips = self.env["hr.payslip"].search(slip_domain)

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

        # Retrieve allowed companies
        allowed_companies = [{"id": 0, "name": _("All Companies (جميع الشركات)")}]
        allowed_companies.extend([
            {"id": c.id, "name": c.name} for c in user_companies
        ])

        # Retrieve departments hierarchically
        dept_domain = [("company_id", "in", [False, target_company_id])] if target_company_id > 0 else [("company_id", "in", [False] + user_companies.ids)]
        raw_departments = self.env["hr.department"].search(dept_domain, order="name asc")

        # Build 3-Tier Department Tree Structure: Root -> Areas/Subgroups -> Branches
        raw_dept_dict = {d.id: d for d in raw_departments}
        root_deps = [d for d in raw_departments if not d.parent_id or d.parent_id.id not in raw_dept_dict]

        structured_departments = []
        for root in root_deps:
            sub_deps = [d for d in raw_departments if d.parent_id and d.parent_id.id == root.id]

            areas_list = []
            if sub_deps:
                for sub in sub_deps:
                    sub_children = [d for d in raw_departments if d.parent_id and d.parent_id.id == sub.id]

                    if sub_children:
                        for s_child in sub_children:
                            branches = self.env["hr.department"].sudo().search([
                                ("id", "child_of", s_child.id),
                                ("id", "!=", s_child.id)
                            ], order="name asc")

                            b_list = [{
                                "id": b.id,
                                "name": b.name,
                                "parent_id": b.parent_id.id if b.parent_id else s_child.id,
                                "company_id": b.company_id.id if b.company_id else 0,
                            } for b in branches]

                            areas_list.append({
                                "id": s_child.id,
                                "name": s_child.name,
                                "parent_id": sub.id,
                                "company_id": s_child.company_id.id if s_child.company_id else 0,
                                "branch_count": len(b_list),
                                "branches": b_list,
                            })
                    else:
                        branches = self.env["hr.department"].sudo().search([
                            ("id", "child_of", sub.id),
                            ("id", "!=", sub.id)
                        ], order="name asc")

                        b_list = [{
                            "id": b.id,
                            "name": b.name,
                            "parent_id": b.parent_id.id if b.parent_id else sub.id,
                            "company_id": b.company_id.id if b.company_id else 0,
                        } for b in branches]

                        areas_list.append({
                            "id": sub.id,
                            "name": sub.name,
                            "parent_id": root.id,
                            "company_id": sub.company_id.id if sub.company_id else 0,
                            "branch_count": len(b_list),
                            "branches": b_list,
                        })
            else:
                branches = self.env["hr.department"].sudo().search([
                    ("id", "child_of", root.id),
                    ("id", "!=", root.id)
                ], order="name asc")

                if branches:
                    b_list = [{
                        "id": b.id,
                        "name": b.name,
                        "parent_id": b.parent_id.id if b.parent_id else root.id,
                        "company_id": b.company_id.id if b.company_id else 0,
                    } for b in branches]

                    areas_list.append({
                        "id": root.id,
                        "name": _("Direct Branches / Units"),
                        "parent_id": root.id,
                        "company_id": root.company_id.id if root.company_id else 0,
                        "branch_count": len(b_list),
                        "branches": b_list,
                    })

            total_branch_count = sum(a["branch_count"] for a in areas_list)

            structured_departments.append({
                "id": root.id,
                "name": root.name,
                "company_id": root.company_id.id if root.company_id else 0,
                "area_count": len(areas_list),
                "total_branch_count": total_branch_count,
                "areas": areas_list,
            })

        # Flat department list for quick reference
        all_departments_flat = [{
            "id": d.id,
            "name": d.name,
            "parent_id": d.parent_id.id if d.parent_id else 0,
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

        proration_ratio = float(selected_days) / float(month_total_days)

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

        for slip in payslips:
            emp = slip.employee_id
            distinct_employee_ids.add(emp.id)
            dep = slip.department_id or emp.department_id
            dep_id = dep.id if dep else 0
            dep_name = dep.name if dep else _("Unassigned / Other")

            if dep_id not in department_dict:
                department_dict[dep_id] = {
                    "department_id": dep_id,
                    "department_name": dep_name,
                    "employee_ids": set(),
                    "headcount": 0,
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

            department_dict[dep_id]["employee_ids"].add(emp.id)

            # Basic & Actual Salary
            slip_basic = getattr(slip, "basic_wage", 0.0) or getattr(slip, "wage", 0.0) or 0.0
            if not slip_basic and hasattr(slip, "contract_id") and slip.contract_id:
                slip_basic = getattr(slip.contract_id, "wage", 0.0) or 0.0
            elif not slip_basic and hasattr(slip, "version_id") and slip.version_id:
                slip_basic = getattr(slip.version_id, "contract_wage", 0.0) or getattr(slip.version_id, "wage", 0.0) or 0.0

            slip_net = 0.0
            slip_gross = 0.0
            slip_allowances = 0.0
            slip_deductions = 0.0
            slip_ssc_emp = 0.0
            slip_ssc_comp = 0.0
            slip_tax = 0.0
            slip_ot_amount = 0.0
            slip_late_amount = 0.0

            # Worked Days Analysis (Exact Hours)
            slip_days = 0.0
            slip_sched_hours = 0.0
            slip_ot_hours = 0.0
            slip_late_hours = 0.0
            slip_wd_ot_amount = 0.0
            slip_wd_late_amount = 0.0

            if hasattr(slip, "worked_days_line_ids") and slip.worked_days_line_ids:
                for wd in slip.worked_days_line_ids:
                    code = (wd.code or "").upper().strip()
                    name = (wd.name or "").lower()
                    hrs = wd.number_of_hours or 0.0
                    days = wd.number_of_days or 0.0
                    amt = getattr(wd, "amount", 0.0) or 0.0

                    is_ot = any(k in code for k in ["OT", "EXTRA", "OVERTIME"]) or any(k in name for k in ["إضافي", "اضافي", "ساعات إضافية"])
                    is_late = any(k in code for k in ["LATE", "UNPAID", "ABSENT", "SHORT", "DELAY", "DED_HOURS"]) or any(k in name for k in ["تأخير", "تاخير", "خصم ساعات", "غياب", "مغادرة"])

                    if is_ot:
                        slip_ot_hours += hrs
                        if amt > 0:
                            slip_wd_ot_amount += amt
                    elif is_late:
                        slip_late_hours += hrs
                        if amt:
                            slip_wd_late_amount += abs(amt)
                    else:
                        # Regular / scheduled worked days
                        if code not in ["OUT"]:
                            slip_days += days
                            slip_sched_hours += hrs if hrs > 0 else (days * 8.0)

            # Fallback for scheduled hours if not tracked on lines
            if not slip_sched_hours and slip_days:
                slip_sched_hours = slip_days * 8.0
            elif not slip_sched_hours and not slip_days:
                slip_sched_hours = 240.0

            # Salary Rule Line Analysis
            if hasattr(slip, "line_ids") and slip.line_ids:
                for line in slip.line_ids:
                    code = (line.code or "").upper().strip()
                    cat_code = (line.category_id.code or "").upper().strip() if line.category_id else ""
                    name = (line.name or "").lower()
                    amt = line.total or 0.0

                    if code == "NET":
                        slip_net = amt
                    elif code in ["GROSS", "GRS", "TOTAL_GROSS"]:
                        slip_gross = amt
                    elif code in ["BASIC", "BASE", "WAGE"] and not slip_basic:
                        slip_basic = amt

                    # Overtime Salary Rule
                    is_ot_line = any(k in code for k in ["OT", "OVERTIME", "EXTRA"]) or any(k in name for k in ["اضافي", "إضافي", "عمل إضافي", "عمل اضافي"])
                    if is_ot_line:
                        slip_ot_amount += amt

                    # Lateness / Deduction Hours Salary Rule
                    is_late_line = any(k in code for k in ["LATE", "DELAY", "SHORTAGE", "DED_HOURS", "UNPAID", "ABS"]) or any(k in name for k in ["تأخير", "تاخير", "خصم ساعات", "خصم تأخير"])
                    if is_late_line:
                        slip_late_amount += abs(amt)

                    # Social Security Analysis
                    is_ss = any(k in code for k in ["SS", "SSC", "GOSI"]) or "ضمان" in name
                    if is_ss:
                        is_comp = any(k in code for k in ["COMP", "COMPANY", "ER", "SSCCO", "SSCP"]) or any(k in name for k in ["شركة", "صاحب العمل"])
                        if is_comp:
                            slip_ssc_comp += abs(amt)
                        else:
                            slip_ssc_emp += abs(amt)

                    # Income Tax
                    is_tax = any(k in code for k in ["TAX", "ITAX", "INCOME_TAX"]) or any(k in name for k in ["ضريبة", "دخل"])
                    if is_tax:
                        slip_tax += abs(amt)

                    # Allowances
                    is_alw = cat_code in ["ALW", "ALLOWANCE", "ALW_RECURRING"] or code in ["ALW", "BONUS", "COMMISSION", "ALLW", "TAKLEEF", "TAKLEF", "TRANS", "HOUSING"] or any(k in name for k in ["علاوة", "مكافأة", "مكافاه", "بدل", "تكليف", "تنقل"])
                    if is_alw and code not in ["GROSS", "NET", "BASIC"]:
                        slip_allowances += amt

                    # Deductions
                    is_ded = cat_code in ["DED", "DEDUCTION"] or code in ["DED", "LOAN", "UNPAID", "PENALTY", "INS", "ADV", "ADVANCE", "DIFF"] or any(k in name for k in ["خصم", "سلفة", "قرض", "عقوبة", "جزاء", "تأمين", "تامين", "مخالفة"])
                    if is_ded and code not in ["NET", "GROSS"]:
                        if not is_ss and not is_tax:
                            slip_deductions += abs(amt)
            else:
                slip_net = getattr(slip, "net_wage", 0.0) or getattr(slip, "total_amount", 0.0) or 0.0
                slip_gross = getattr(slip, "gross_wage", 0.0) or slip_basic

            # Fallbacks for Overtime Amount if rule didn't compute an amount
            hourly_rate = (slip_basic / 240.0) if slip_basic else 0.0
            if not slip_ot_amount:
                if slip_wd_ot_amount:
                    slip_ot_amount = slip_wd_ot_amount
                elif slip_ot_hours > 0 and hourly_rate > 0:
                    slip_ot_amount = round(slip_ot_hours * hourly_rate * 1.25, 3)

            # Fallbacks for Lateness Amount
            if not slip_late_amount:
                if slip_wd_late_amount:
                    slip_late_amount = slip_wd_late_amount
                elif slip_late_hours > 0 and hourly_rate > 0:
                    slip_late_amount = round(slip_late_hours * hourly_rate, 3)

            # Fallbacks for Gross & Net
            if not slip_gross:
                slip_gross = getattr(slip, "gross_wage", 0.0) or (slip_basic + slip_allowances + slip_ot_amount)
            if not slip_net:
                total_all_deductions = slip_deductions + slip_ssc_emp + slip_tax + slip_late_amount
                slip_net = getattr(slip, "net_wage", 0.0) or max(slip_gross - total_all_deductions, 0.0)

            # Calendar-Exact Employee Daily Cost (using actual target month days)
            slip_daily_cost = (slip_gross + slip_ssc_comp) / float(month_total_days)

            # Apply proration ratio to scale monthly payslip figures for the selected date range
            p_basic = slip_basic * proration_ratio
            p_gross = slip_gross * proration_ratio
            p_net = slip_net * proration_ratio
            p_allowances = slip_allowances * proration_ratio
            p_deductions = (slip_deductions + slip_late_amount) * proration_ratio
            p_ssc_emp = slip_ssc_emp * proration_ratio
            p_ssc_comp = slip_ssc_comp * proration_ratio
            p_tax = slip_tax * proration_ratio
            p_ot_amount = slip_ot_amount * proration_ratio
            p_ot_hours = slip_ot_hours * proration_ratio
            p_late_hours = slip_late_hours * proration_ratio
            p_late_amount = slip_late_amount * proration_ratio
            p_sched_hours = slip_sched_hours * proration_ratio
            p_working_days = slip_days * proration_ratio

            # Accumulate global totals
            total_basic_salary += p_basic
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

            # Department breakdown accumulation
            dep_row = department_dict[dep_id]
            dep_row["basic_salary"] += p_basic
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

        # Finalize department rows with zero-latency in-memory hierarchy lookup
        dept_children_map = defaultdict(set)
        dept_parent_map = {d.id: d.parent_id.id for d in raw_departments if d.parent_id}
        for d in raw_departments:
            dept_children_map[d.id].add(d.id)
            curr = d.id
            while curr in dept_parent_map:
                p_id = dept_parent_map[curr]
                dept_children_map[p_id].add(d.id)
                curr = p_id

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
                if department_ids:
                    raw_dep_ids = [int(d) for d in department_ids if int(d) > 0]
                    if raw_dep_ids:
                        all_target_dep_ids = self.env["hr.department"].search([("id", "child_of", raw_dep_ids)]).ids
                        att_domain.append(("employee_id.department_id", "in", all_target_dep_ids))

                attendances = self.env["hr.attendance"].sudo().search(att_domain)
                present_employees = attendances.mapped("employee_id")
                today_present_count = len(present_employees)

                for emp in present_employees:
                    if emp.department_id:
                        dept_present_map[emp.department_id.id] += 1

                emp_domain = [("active", "=", True)]
                if target_company_id > 0:
                    emp_domain.append(("company_id", "=", target_company_id))
                if department_ids:
                    raw_dep_ids = [int(d) for d in department_ids if int(d) > 0]
                    if raw_dep_ids:
                        all_target_dep_ids = self.env["hr.department"].search([("id", "child_of", raw_dep_ids)]).ids
                        emp_domain.append(("department_id", "in", all_target_dep_ids))

                all_active_employees = self.env["hr.employee"].sudo().search(emp_domain)
                today_absent_count = max(len(all_active_employees) - today_present_count, 0)

                # Compute exact live daily cost of PRESENT employees vs ABSENT employees
                avg_wage_fallback = (total_gross_salary / len(distinct_employee_ids)) if distinct_employee_ids else 500.0
                for emp in all_active_employees:
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

        department_list = []
        for d_id, row in department_dict.items():
            row["headcount"] = len(row["employee_ids"])
            del row["employee_ids"]
            row["calendar_days"] = selected_days
            row["daily_cost"] = round(row["daily_cost"], 3)
            row["avg_daily_cost_per_emp"] = round(row["daily_cost"] / row["headcount"], 3) if row["headcount"] else 0.0

            # POS Sales & Labor Cost % for Retail Branches (Direct branch matching + non-duplicated aggregation)
            pos_sales = pos_sales_by_dept.get(d_id, 0.0)
            pos_orders = pos_orders_by_dept.get(d_id, 0)
            present_cnt = dept_present_map.get(d_id, 0)

            if not pos_sales and d_id > 0:
                child_ids = dept_children_map.get(d_id, set()) - {d_id}
                unrepresented_children = [cid for cid in child_ids if cid not in department_dict]
                if unrepresented_children:
                    pos_sales = sum(pos_sales_by_dept.get(cid, 0.0) for cid in unrepresented_children)

            if not pos_orders and d_id > 0:
                child_ids = dept_children_map.get(d_id, set()) - {d_id}
                unrepresented_children = [cid for cid in child_ids if cid not in department_dict]
                if unrepresented_children:
                    pos_orders = sum(pos_orders_by_dept.get(cid, 0) for cid in unrepresented_children)

            if not present_cnt and d_id > 0:
                child_ids = dept_children_map.get(d_id, set()) - {d_id}
                unrepresented_children = [cid for cid in child_ids if cid not in department_dict]
                if unrepresented_children:
                    present_cnt = sum(dept_present_map.get(cid, 0) for cid in unrepresented_children)

            row["pos_sales"] = round(pos_sales, 3)
            row["pos_orders"] = pos_orders
            row["present_headcount"] = present_cnt
            row["sales_per_present_emp"] = round((pos_sales / present_cnt), 3) if present_cnt else (round(pos_sales / row["headcount"], 3) if row["headcount"] else 0.0)
            row["orders_per_present_emp"] = round((pos_orders / present_cnt), 1) if present_cnt else (round(pos_orders / row["headcount"], 1) if row["headcount"] else 0.0)
            row["sales_per_total_emp"] = round((pos_sales / row["headcount"]), 3) if row["headcount"] else 0.0

            period_dept_labor_cost = row["daily_cost"] * float(selected_days)
            row["pos_labor_cost_pct"] = round((period_dept_labor_cost / pos_sales * 100.0), 1) if pos_sales else 0.0
            row["sales_per_jod_labor"] = round((pos_sales / period_dept_labor_cost), 2) if period_dept_labor_cost else 0.0

            # Factory Production Output Ratios
            mrp_qty = mrp_qty_by_dept.get(d_id, 0.0)
            if not mrp_qty and d_id > 0:
                child_ids = dept_children_map.get(d_id, set()) - {d_id}
                unrepresented_children = [cid for cid in child_ids if cid not in department_dict]
                if unrepresented_children:
                    mrp_qty = sum(mrp_qty_by_dept.get(cid, 0.0) for cid in unrepresented_children)

            row["mrp_qty"] = round(mrp_qty, 2)
            row["labor_cost_per_unit"] = round((period_dept_labor_cost / mrp_qty), 3) if mrp_qty else 0.0

            department_list.append(row)

        department_list.sort(key=lambda x: x["net_salary"], reverse=True)

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
        total_pos_sales = sum(d["pos_sales"] for d in department_list)
        ceo_sales_labor_roi = round((total_pos_sales / total_employer_payroll_expense), 2) if total_employer_payroll_expense else 0.0

        retail_depts = [d for d in department_list if d["pos_sales"] > 0]
        top_profitable_branches = sorted(retail_depts, key=lambda x: x["sales_per_jod_labor"], reverse=True)[:3]
        bottom_profitable_branches = sorted(retail_depts, key=lambda x: x["pos_labor_cost_pct"], reverse=True)[:3]

        factory_depts = [d for d in department_list if d["mrp_qty"] > 0]
        factory_unit_cost_avg = round(sum(d["labor_cost_per_unit"] for d in factory_depts) / len(factory_depts), 3) if factory_depts else 0.0

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
            "avg_salary_per_emp": round(total_net_salary / len(distinct_employee_ids), 3) if distinct_employee_ids else 0.0,
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
                "headcount": len(distinct_employee_ids),
                "payslip_count": len(payslips),
                "bank_count": bank_count,
                "bank_amount": round(bank_amount, 3),
                "cash_count": cash_count,
                "cash_amount": round(cash_amount, 3),
                "avg_salary_per_emp": round(total_net_salary / len(distinct_employee_ids), 3) if distinct_employee_ids else 0.0,
                "total_daily_cost": round(total_daily_cost, 3),
                "avg_daily_cost_per_emp": round(total_daily_cost / len(distinct_employee_ids), 3) if distinct_employee_ids else 0.0,
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
            ("date_from", "<=", end_date),
            ("date_to", ">=", start_date),
        ]
        target_payrun_id = int(payrun_id) if payrun_id and int(payrun_id) > 0 else 0
        if target_payrun_id > 0:
            slip_domain.append(("payslip_run_id", "=", target_payrun_id))

        if target_company_id > 0:
            slip_domain.append(("company_id", "=", target_company_id))
        else:
            slip_domain.append(("company_id", "in", user_companies.ids))

        if department_ids:
            raw_dep_ids = [int(d) for d in department_ids if int(d) > 0]
            if raw_dep_ids:
                all_target_dep_ids = self.env["hr.department"].search([("id", "child_of", raw_dep_ids)]).ids
                slip_domain.extend([
                    "|",
                    ("department_id", "in", all_target_dep_ids),
                    ("employee_id.department_id", "in", all_target_dep_ids),
                ])

        payslips = self.env["hr.payslip"].search(slip_domain)
        slip_ids = payslips.ids

        if metric_type == "headcount":
            emp_ids = payslips.mapped("employee_id").ids
            return {
                "name": _("Active Payroll Employees (%s)") % len(emp_ids),
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
