# -*- coding: utf-8 -*-
from datetime import datetime, date, timedelta
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
        user_company = self.env.company
        target_company_id = int(company_id) if company_id else user_company.id

        # Determine date ranges
        today = fields.Date.today()
        if not date_from or not date_to:
            # Default to current month start and end
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

        # Base Domain for Payslips
        slip_domain = [
            ("state", "not in", ["cancel"]),
            ("company_id", "=", target_company_id),
        ]

        if payrun_id and int(payrun_id) > 0:
            slip_domain.append(("payslip_run_id", "=", int(payrun_id)))
        else:
            slip_domain.extend([
                ("date_from", "<=", end_date),
                ("date_to", ">=", start_date),
            ])

        if department_ids:
            dep_ids = [int(d) for d in department_ids if int(d) > 0]
            if dep_ids:
                slip_domain.append(("department_id", "in", dep_ids))

        payslips = self.env["hr.payslip"].search(slip_domain)

        # Retrieve payrun batches for dropdown
        payruns = self.env["hr.payslip.run"].search([
            ("company_id", "=", target_company_id),
        ], order="date_start desc", limit=20)
        payrun_batches = [{
            "id": p.id,
            "name": p.name or _("Batch %s") % p.id,
            "date_start": str(p.date_start or ""),
            "date_end": str(p.date_end or ""),
            "state": p.state if hasattr(p, "state") else "",
        } for p in payruns]

        # Retrieve all active departments for pills
        all_departments = self.env["hr.department"].search_read(
            [("company_id", "in", [False, target_company_id])],
            ["id", "name"],
            order="name asc",
        )

        # Retrieve allowed companies
        allowed_companies = self.env["res.company"].search_read(
            [("id", "in", self.env.user.company_ids.ids)],
            ["id", "name"],
            order="name asc",
        )

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
        total_working_days = 0.0

        bank_count = 0
        bank_amount = 0.0
        cash_count = 0
        cash_amount = 0.0

        distinct_employee_ids = set()
        department_dict = {}

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
                    "income_tax": 0.0,
                    "working_days": 0.0,
                }

            department_dict[dep_id]["employee_ids"].add(emp.id)

            # Basic & Actual Salary
            slip_basic = getattr(slip, "basic_wage", 0.0) or 0.0
            slip_wage = getattr(slip, "wage", 0.0) or 0.0
            contract_wage = 0.0
            if hasattr(slip, "contract_id") and slip.contract_id:
                contract_wage = getattr(slip.contract_id, "wage", 0.0) or 0.0
            elif hasattr(slip, "version_id") and slip.version_id:
                contract_wage = getattr(slip.version_id, "contract_wage", 0.0) or getattr(slip.version_id, "wage", 0.0) or 0.0

            slip_basic = slip_basic or contract_wage or slip_wage

            # Extract line categories from line_ids
            slip_net = 0.0
            slip_gross = 0.0
            slip_allowances = 0.0
            slip_deductions = 0.0
            slip_ssc = 0.0
            slip_tax = 0.0
            slip_ot_amount = 0.0
            slip_late_amount = 0.0

            if hasattr(slip, "line_ids") and slip.line_ids:
                for line in slip.line_ids:
                    code = (line.code or "").upper().strip()
                    cat_code = (line.category_id.code or "").upper().strip() if line.category_id else ""
                    name = (line.name or "").lower()
                    amt = line.total or 0.0

                    if code == "NET":
                        slip_net = amt
                    elif code in ["GROSS", "GRS"]:
                        slip_gross = amt
                    elif code in ["BASIC", "BASE"] and not slip_basic:
                        slip_basic = amt
                    elif "ACTUAL" in code or "فعلي" in name:
                        slip_actual_salary += amt

                    # Allowance Categories
                    if cat_code in ["ALW", "ALLOWANCE"] or code in ["ALW", "BONUS", "COMMISSION", "ALLW", "OVERTIME", "OT"] or any(k in name for k in ["علاوة", "مكافأة", "إضافي", "اضافي", "بدل"]):
                        if code not in ["GROSS", "NET", "BASIC"]:
                            slip_allowances += amt

                    # Deductions Categories
                    if cat_code in ["DED", "DEDUCTION"] or code in ["DED", "LOAN", "UNPAID", "LATE", "PENALTY", "INS"] or any(k in name for k in ["خصم", "سلفة", "قرض", "عقوبة", "تأمين", "تامين", "مخالفة"]):
                        if code not in ["NET", "GROSS"]:
                            slip_deductions += abs(amt)

                    # Social Security
                    if "SS" in code or "SSC" in code or "ضمان" in name:
                        if "COMP" in code or "شركة" in name:
                            total_social_security_comp += abs(amt)
                        else:
                            slip_ssc += abs(amt)

                    # Income Tax
                    if "TAX" in code or "ITAX" in code or "ضريبة" in name:
                        slip_tax += abs(amt)

                    # Overtime
                    if "OT" in code or "OVERTIME" in code or "اضافي" in name or "إضافي" in name:
                        slip_ot_amount += amt

                    # Lateness
                    if "LATE" in code or "تأخير" in name or "تاخير" in name or "خصم ساعات" in name:
                        slip_late_amount += abs(amt)
            else:
                slip_net = getattr(slip, "net_wage", 0.0) or getattr(slip, "total_amount", 0.0) or 0.0
                slip_gross = getattr(slip, "gross_wage", 0.0) or slip_basic

            # Fallback if net/gross was 0 from lines
            if not slip_net:
                slip_net = getattr(slip, "net_wage", 0.0) or getattr(slip, "total_amount", 0.0) or slip_basic
            if not slip_gross:
                slip_gross = getattr(slip, "gross_wage", 0.0) or slip_basic

            # Worked Days Analysis (Hours, Overtime, Days)
            slip_days = 0.0
            slip_ot_hours = 0.0
            slip_late_hours = 0.0

            if hasattr(slip, "worked_days_line_ids") and slip.worked_days_line_ids:
                for wd in slip.worked_days_line_ids:
                    code = (wd.code or "").upper().strip()
                    name = (wd.name or "").lower()
                    if code not in ["OUT"]:
                        slip_days += wd.number_of_days or 0.0
                    if "OT" in code or "EXTRA" in code or "اضافي" in name or "إضافي" in name:
                        slip_ot_hours += wd.number_of_hours or 0.0
                    if "LATE" in code or "تأخير" in name or "تاخير" in name or "خصم" in name:
                        slip_late_hours += wd.number_of_hours or 0.0

            # Accumulate global totals
            total_basic_salary += slip_basic
            total_gross_salary += slip_gross
            total_net_salary += slip_net
            total_allowances += slip_allowances
            total_deductions += slip_deductions
            total_social_security_emp += slip_ssc
            total_income_tax += slip_tax
            total_overtime_amount += slip_ot_amount
            total_overtime_hours += slip_ot_hours
            total_lateness_hours += slip_late_hours
            total_lateness_amount += slip_late_amount
            total_working_days += slip_days

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
            dep_row["deductions"] += slip_deductions
            dep_row["social_security"] += slip_ssc
            dep_row["income_tax"] += slip_tax
            dep_row["overtime_amount"] += slip_ot_amount
            dep_row["overtime_hours"] += slip_ot_hours
            dep_row["lateness_hours"] += slip_late_hours
            dep_row["lateness_amount"] += slip_late_amount
            dep_row["working_days"] += slip_days

        # Finalize department rows
        department_list = []
        for d_id, row in department_dict.items():
            row["headcount"] = len(row["employee_ids"])
            del row["employee_ids"]
            department_list.append(row)

        department_list.sort(key=lambda x: x["net_salary"], reverse=True)

        # Operational highlights (Top OT, Top Lateness, Top Headcount)
        top_ot_departments = sorted(department_list, key=lambda x: x["overtime_hours"], reverse=True)[:5]
        top_late_departments = sorted(department_list, key=lambda x: x["lateness_hours"], reverse=True)[:5]
        top_headcount_departments = sorted(department_list, key=lambda x: x["headcount"], reverse=True)[:5]

        # Attendance reconciliation overview
        scheduled_hours = total_working_days * 8.0
        approved_hours = max(scheduled_hours + total_overtime_hours - total_lateness_hours, 0.0)

        data = {
            "date_from": str(start_date),
            "date_to": str(end_date),
            "selected_company_id": target_company_id,
            "selected_payrun_id": int(payrun_id) if payrun_id else 0,
            "payrun_batches": payrun_batches,
            "all_departments": all_departments,
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
                "scheduled_hours": round(scheduled_hours, 2),
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
        """Returns window action with pre-filtered domain corresponding to clicked KPI card."""
        user_company = self.env.company
        target_company_id = int(company_id) if company_id else user_company.id

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
            ("company_id", "=", target_company_id),
        ]
        if payrun_id and int(payrun_id) > 0:
            slip_domain.append(("payslip_run_id", "=", int(payrun_id)))
        else:
            slip_domain.extend([
                ("date_from", "<=", end_date),
                ("date_to", ">=", start_date),
            ])

        if department_ids:
            dep_ids = [int(d) for d in department_ids if int(d) > 0]
            if dep_ids:
                slip_domain.append(("department_id", "in", dep_ids))

        payslips = self.env["hr.payslip"].search(slip_domain)
        slip_ids = payslips.ids

        # 1. Headcount Drilldown -> Employees
        if metric_type == "headcount":
            emp_ids = payslips.mapped("employee_id").ids
            return {
                "name": _("Active Payroll Employees (%s)") % len(emp_ids),
                "type": "ir.actions.act_window",
                "res_model": "hr.employee",
                "view_mode": "list,kanban,form",
                "domain": [("id", "in", emp_ids)],
                "context": {"create": False},
                "target": "current",
            }

        # 2. Overtime Drilldown -> Payslip Worked Days / Overtime Lines
        elif metric_type in ["overtime", "overtime_hours", "overtime_amount"]:
            return {
                "name": _("Overtime & Extra Hours Analysis"),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip.worked_days",
                "view_mode": "list,pivot,graph",
                "domain": [
                    ("payslip_id", "in", slip_ids),
                    "|", "|",
                    ("code", "ilike", "OT"),
                    ("code", "ilike", "EXTRA"),
                    ("name", "ilike", "إضافي"),
                ],
                "context": {"create": False, "search_default_group_by_payslip": 1},
                "target": "current",
            }

        # 3. Lateness Drilldown -> Payslip Worked Days Lateness
        elif metric_type in ["lateness", "lateness_hours", "lateness_amount"]:
            return {
                "name": _("Lateness & Subtracted Hours Analysis"),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip.worked_days",
                "view_mode": "list,pivot,graph",
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

        # 4. Social Security & Tax Drilldown -> Payslip Lines
        elif metric_type in ["social_security", "social_security_company"]:
            return {
                "name": _("Social Security Deduction Lines"),
                "type": "ir.actions.act_window",
                "res_model": "hr.payslip.line",
                "view_mode": "list,pivot,graph",
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
                "domain": [("id", "in", bank_slip_ids)],
                "context": {"create": False},
                "target": "current",
            }

        # Default fallback: Payslips List
        return {
            "name": _("Executive Payslips Drilldown"),
            "type": "ir.actions.act_window",
            "res_model": "hr.payslip",
            "view_mode": "list,kanban,pivot,graph,form",
            "domain": [("id", "in", slip_ids)],
            "context": {"create": False},
            "target": "current",
        }
