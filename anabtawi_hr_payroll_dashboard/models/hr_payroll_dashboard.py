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
    def get_dashboard_data(self, date_from=None, date_to=None, payrun_id=None, company_id=None, department_ids=None):
        """Calculates and aggregates comprehensive HR, Payroll, Overtime, and Attendance metrics."""
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

        # Base Domain for Payslips (Includes ALL validated payslips: bulk & separate)
        slip_domain = [
            ("state", "not in", ["cancel"]),
            ("date_from", "<=", end_date),
            ("date_to", ">=", start_date),
        ]
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

        # Build department tree (parent departments and their children)
        # Find all parent departments (no parent or parent not in current set)
        dept_ids_set = set(raw_departments.ids)
        parent_departments = []
        children_by_parent = {}

        for dep in raw_departments:
            p_id = dep.parent_id.id if dep.parent_id and dep.parent_id.id in dept_ids_set else 0
            if p_id == 0:
                parent_departments.append({
                    "id": dep.id,
                    "name": dep.name,
                    "company_id": dep.company_id.id if dep.company_id else 0,
                    "child_count": 0,
                    "children": [],
                })
            else:
                if p_id not in children_by_parent:
                    children_by_parent[p_id] = []
                children_by_parent[p_id].append({
                    "id": dep.id,
                    "name": dep.name,
                    "parent_id": p_id,
                    "company_id": dep.company_id.id if dep.company_id else 0,
                })

        # Attach children and counts to parents
        for p in parent_departments:
            c_list = children_by_parent.get(p["id"], [])
            p["children"] = c_list
            p["child_count"] = len(c_list)

        # Flat department list for quick reference
        all_departments_flat = [{
            "id": d.id,
            "name": d.name,
            "parent_id": d.parent_id.id if d.parent_id else 0,
        } for d in raw_departments]

        # Calendar days in selected month period
        calendar_days = (end_date - start_date).days + 1
        if calendar_days <= 0:
            calendar_days = 30

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

        # Pre-fetch POS Sales data for retail branches if available
        pos_sales_by_dept = defaultdict(float)
        if "pos.order" in self.env:
            try:
                pos_domain = [
                    ("state", "in", ["paid", "done", "invoiced"]),
                    ("date_order", ">=", datetime.combine(start_date, datetime.min.time())),
                    ("date_order", "<=", datetime.combine(end_date, datetime.max.time())),
                ]
                if target_company_id > 0:
                    pos_domain.append(("company_id", "=", target_company_id))

                pos_orders = self.env["pos.order"].sudo().search(pos_domain)
                for p_order in pos_orders:
                    cfg = p_order.config_id or (p_order.session_id.config_id if getattr(p_order, "session_id", False) else False)
                    cfg_id = cfg.id if cfg else 0
                    d_id = pos_config_dept_map.get(cfg_id, 0)
                    if not d_id and cfg:
                        d_id = getattr(cfg, "department_id", False)
                        d_id = d_id.id if d_id else 0
                    if d_id:
                        pos_sales_by_dept[d_id] += p_order.amount_total
            except Exception as e:
                _logger.warning("POS Order search skipped in payroll dashboard: %s", e)

        # Pre-fetch Manufacturing Output data for factory lines if available
        mrp_qty_by_dept = defaultdict(float)
        if "mrp.production" in self.env:
            try:
                mrp_domain = [
                    ("state", "=", "done"),
                    ("date_finished", ">=", datetime.combine(start_date, datetime.min.time())),
                    ("date_finished", "<=", datetime.combine(end_date, datetime.max.time())),
                ]
                if target_company_id > 0:
                    mrp_domain.append(("company_id", "=", target_company_id))
                mrp_orders = self.env["mrp.production"].sudo().search(mrp_domain)
                for m_order in mrp_orders:
                    m_dept = getattr(m_order, "department_id", False)
                    if m_dept:
                        mrp_qty_by_dept[m_dept.id] += getattr(m_order, "qty_produced", 0.0) or 0.0
            except Exception as e:
                _logger.warning("MRP Production search skipped in payroll dashboard: %s", e)

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

            # Calendar-Exact Employee Daily Cost
            slip_daily_cost = (slip_gross + slip_ssc_comp) / float(calendar_days)

            # Accumulate global totals
            total_basic_salary += slip_basic
            total_gross_salary += slip_gross
            total_net_salary += slip_net
            total_allowances += slip_allowances
            total_deductions += (slip_deductions + slip_late_amount)
            total_social_security_emp += slip_ssc_emp
            total_social_security_comp += slip_ssc_comp
            total_income_tax += slip_tax
            total_overtime_amount += slip_ot_amount
            total_overtime_hours += slip_ot_hours
            total_lateness_hours += slip_late_hours
            total_lateness_amount += slip_late_amount
            total_scheduled_hours += slip_sched_hours
            total_working_days += slip_days
            total_daily_cost += slip_daily_cost

            # Bank vs Cash Payment analysis
            has_bank = False
            if hasattr(emp, "bank_account_id") and emp.bank_account_id:
                has_bank = True
            elif hasattr(emp, "bank_account_ids") and emp.bank_account_ids:
                has_bank = True

            if has_bank:
                bank_count += 1
                bank_amount += slip_net
            else:
                cash_count += 1
                cash_amount += slip_net

            # Department breakdown accumulation
            dep_row = department_dict[dep_id]
            dep_row["basic_salary"] += slip_basic
            dep_row["gross_salary"] += slip_gross
            dep_row["net_salary"] += slip_net
            dep_row["allowances"] += slip_allowances
            dep_row["deductions"] += (slip_deductions + slip_late_amount)
            dep_row["social_security"] += slip_ssc_emp
            dep_row["social_security_comp"] += slip_ssc_comp
            dep_row["income_tax"] += slip_tax
            dep_row["overtime_amount"] += slip_ot_amount
            dep_row["overtime_hours"] += slip_ot_hours
            dep_row["lateness_hours"] += slip_late_hours
            dep_row["lateness_amount"] += slip_late_amount
            dep_row["working_days"] += slip_days
            dep_row["daily_cost"] += slip_daily_cost

        # Finalize department rows
        department_list = []
        dept_children_map = {}
        for d_id, row in department_dict.items():
            row["headcount"] = len(row["employee_ids"])
            del row["employee_ids"]
            row["calendar_days"] = calendar_days
            row["daily_cost"] = round(row["daily_cost"], 3)
            row["avg_daily_cost_per_emp"] = round(row["daily_cost"] / row["headcount"], 3) if row["headcount"] else 0.0

            if d_id > 0:
                if d_id not in dept_children_map:
                    dept_children_map[d_id] = set(self.env["hr.department"].sudo().search([("id", "child_of", d_id)]).ids)
                relevant_dept_ids = dept_children_map[d_id]
            else:
                relevant_dept_ids = {0}

            # POS Sales & Labor Cost % for Retail Branches (sums department and all child branches)
            pos_sales = sum(pos_sales_by_dept.get(cid, 0.0) for cid in relevant_dept_ids)
            row["pos_sales"] = round(pos_sales, 3)
            monthly_dept_cost = row["daily_cost"] * float(calendar_days)
            row["pos_labor_cost_pct"] = round((monthly_dept_cost / pos_sales * 100.0), 1) if pos_sales else 0.0
            row["sales_per_jod_labor"] = round((pos_sales / monthly_dept_cost), 2) if monthly_dept_cost else 0.0

            # Factory Production Output Ratios
            mrp_qty = sum(mrp_qty_by_dept.get(cid, 0.0) for cid in relevant_dept_ids)
            row["mrp_qty"] = round(mrp_qty, 2)
            row["labor_cost_per_unit"] = round((monthly_dept_cost / mrp_qty), 3) if mrp_qty else 0.0

            department_list.append(row)

        department_list.sort(key=lambda x: x["net_salary"], reverse=True)

        top_ot_departments = sorted(department_list, key=lambda x: x["overtime_hours"], reverse=True)[:5]
        top_late_departments = sorted(department_list, key=lambda x: x["lateness_hours"], reverse=True)[:5]
        top_headcount_departments = sorted(department_list, key=lambda x: x["headcount"], reverse=True)[:5]

        approved_hours = max(total_scheduled_hours + total_overtime_hours - total_lateness_hours, 0.0)
        total_employer_payroll_expense = round(total_gross_salary + total_social_security_comp, 3)
        overtime_cost_ratio = round((total_overtime_amount / total_gross_salary * 100.0), 1) if total_gross_salary else 0.0

        data = {
            "date_from": str(start_date),
            "date_to": str(end_date),
            "calendar_days": calendar_days,
            "selected_company_id": target_company_id,
            "selected_payrun_id": int(payrun_id) if payrun_id else 0,
            "payrun_batches": payrun_batches,
            "all_departments": all_departments_flat,
            "parent_departments": parent_departments,
            "all_companies": allowed_companies,
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


class PosConfigInheritDashboard(models.Model):
    _inherit = "pos.config"

    department_id = fields.Many2one(
        "hr.department",
        string="HR Department / Branch",
        help="Link this Point of Sale shop/register to an HR Department for executive sales & labor cost reporting."
    )
