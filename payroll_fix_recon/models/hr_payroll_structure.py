# -*- coding: utf-8 -*-
"""Reconciliation salary rules, created once per salary structure (idempotent)."""
from odoo import api, models

RULES = [
    {
        'code': 'ATT_RECON_VAR', 'name': 'Attendance Reconciled Hours Variance', 'category': 'hr_payroll.BASIC',
        'sequence': 50, 'appears_on_payslip': False, 'condition_select': 'none',
        'amount_python_compute': "# informational: 0.0 so basic pay is untouched\nresult = 0.0\n",
    },
    {
        'code': 'OT_NET', 'name': 'Net Reconciled Overtime', 'category': 'hr_payroll.ALW',
        'sequence': 60, 'appears_on_payslip': True, 'condition_select': 'python',
        'condition_python': "result = round(payslip.attendance_net_reconciled, 2) > 0.01\n",
        'amount_python_compute': "# banked to Extra Hours, never paid as cash on the monthly slip\nresult = 0.0\n",
    },
    {
        'code': 'DED_UNDERTIME', 'name': 'Attendance Deduction', 'category': 'hr_payroll.DED',
        'sequence': 70, 'appears_on_payslip': True, 'condition_select': 'python',
        'condition_python': "result = round(payslip.undertime_cash_deduction_hours, 2) >= 0.01\n",
        'amount_python_compute': (
            "# lateness + absent hours NOT covered by Extra Hours / PTO / Annual Leave (step 4)\n"
            "hours = round(payslip.undertime_cash_deduction_hours, 2)\n"
            "wage = employee.wage or 0.0\n"
            "result = round(min(hours * wage / 240.0, wage), 3) if hours >= 0.01 else 0.0\n"),
    },
    {
        'code': 'DED_ANNUAL_LEAVE', 'name': 'Negative Annual Leave Deduction', 'category': 'hr_payroll.DED',
        'sequence': 75, 'appears_on_payslip': True, 'condition_select': 'python',
        'condition_python': (
            "v = version or (employee.version_id if (employee and 'version_id' in employee._fields) else False)\n"
            "wage = (v.wage if (v and 'wage' in v._fields) else 0.0) or employee.wage or 0.0\n"
            "annual = inputs['CLEAR_ANNUAL'].amount if 'CLEAR_ANNUAL' in inputs else 0.0\n"
            "accrual_amount = 0.0\n"
            "if 'CLEAR_ANNUAL' in inputs and employee and payslip and wage > 0 and payslip.date_to:\n"
            "    end_date = payslip.date_to\n"
            "    start_date = (\n"
            "        (v.contract_date_start if (v and 'contract_date_start' in v._fields) else None)\n"
            "        or (v.date_start if (v and 'date_start' in v._fields) else None)\n"
            "        or (employee.contract_date_start if (employee and 'contract_date_start' in employee._fields) else None)\n"
            "        or (employee.first_contract_date if (employee and 'first_contract_date' in employee._fields) else None)\n"
            "    )\n"
            "    if start_date and start_date <= end_date:\n"
            "        years = end_date.year - start_date.year\n"
            "        if (end_date.month, end_date.day) < (start_date.month, start_date.day):\n"
            "            years -= 1\n"
            "        monthly_accrual = 1.75 if years >= 5 else 1.17\n"
            "        month = end_date.month\n"
            "        year = end_date.year\n"
            "        if month in (1, 3, 5, 7, 8, 10, 12):\n"
            "            days_in_month = 31\n"
            "        elif month in (4, 6, 9, 11):\n"
            "            days_in_month = 30\n"
            "        elif month == 2:\n"
            "            leap_year = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))\n"
            "            days_in_month = 29 if leap_year else 28\n"
            "        else:\n"
            "            days_in_month = 30\n"
            "        accrued_days = monthly_accrual * end_date.day / days_in_month\n"
            "        accrual_amount = accrued_days * wage / 30.0\n"
            "result = 'CLEAR_ANNUAL' in inputs and (annual + accrual_amount) < 0\n"
        ),
        'amount_python_compute': (
            "v = version or (employee.version_id if (employee and 'version_id' in employee._fields) else False)\n"
            "wage = (v.wage if (v and 'wage' in v._fields) else 0.0) or employee.wage or 0.0\n"
            "annual = inputs['CLEAR_ANNUAL'].amount if 'CLEAR_ANNUAL' in inputs else 0.0\n"
            "accrual_amount = 0.0\n"
            "if 'CLEAR_ANNUAL' in inputs and employee and payslip and wage > 0 and payslip.date_to:\n"
            "    end_date = payslip.date_to\n"
            "    start_date = (\n"
            "        (v.contract_date_start if (v and 'contract_date_start' in v._fields) else None)\n"
            "        or (v.date_start if (v and 'date_start' in v._fields) else None)\n"
            "        or (employee.contract_date_start if (employee and 'contract_date_start' in employee._fields) else None)\n"
            "        or (employee.first_contract_date if (employee and 'first_contract_date' in employee._fields) else None)\n"
            "    )\n"
            "    if start_date and start_date <= end_date:\n"
            "        years = end_date.year - start_date.year\n"
            "        if (end_date.month, end_date.day) < (start_date.month, start_date.day):\n"
            "            years -= 1\n"
            "        monthly_accrual = 1.75 if years >= 5 else 1.17\n"
            "        month = end_date.month\n"
            "        year = end_date.year\n"
            "        if month in (1, 3, 5, 7, 8, 10, 12):\n"
            "            days_in_month = 31\n"
            "        elif month in (4, 6, 9, 11):\n"
            "            days_in_month = 30\n"
            "        elif month == 2:\n"
            "            leap_year = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))\n"
            "            days_in_month = 29 if leap_year else 28\n"
            "        else:\n"
            "            days_in_month = 30\n"
            "        accrued_days = monthly_accrual * end_date.day / days_in_month\n"
            "        accrual_amount = accrued_days * wage / 30.0\n"
            "net_annual = annual + accrual_amount\n"
            "result = round(abs(net_annual), 3) if ('CLEAR_ANNUAL' in inputs and net_annual < 0) else 0.0\n"
        ),
    },
    {
        'code': 'TERM_EXTRA', 'name': 'Termination: Extra Hours Settlement', 'category': 'hr_payroll.ALW',
        'sequence': 80, 'appears_on_payslip': True, 'condition_select': 'python',
        'condition_python': "result = 'CLEAR_EXTRA' in inputs and inputs['CLEAR_EXTRA'].amount > 0\n",
        'amount_python_compute': "result = round(inputs['CLEAR_EXTRA'].amount, 3)\n",
    },
    {
        'code': 'TERM_PTO', 'name': 'Termination: Paid Time Off Settlement', 'category': 'hr_payroll.ALW',
        'sequence': 81, 'appears_on_payslip': True, 'condition_select': 'python',
        'condition_python': "result = 'CLEAR_PTO' in inputs and inputs['CLEAR_PTO'].amount > 0\n",
        'amount_python_compute': "result = round(inputs['CLEAR_PTO'].amount, 3)\n",
    },
    {
        'code': 'TERM_ANNUAL', 'name': 'Termination: Annual Leave Settlement', 'category': 'hr_payroll.ALW',
        'sequence': 82, 'appears_on_payslip': True, 'condition_select': 'python',
        'condition_python': "result = 'CLEAR_ANNUAL' in inputs and inputs['CLEAR_ANNUAL'].amount > 0\n",
        'amount_python_compute': (
            "# negative balances are handled by DED_ANNUAL_LEAVE\n"
            "result = round(inputs['CLEAR_ANNUAL'].amount, 3)\n"),
    },
    {
        'code': 'ACTUAL', 'name': 'Actual Salary', 'category': 'hr_payroll.NET',
        'sequence': 90, 'appears_on_payslip': True, 'condition_select': 'none',
        'amount_python_compute': (
            "# calendar days - out of contract - unpaid - partial-pay types (e.g. Work Injury 7.5%).\n"
            "# ABSENT days are NOT cut here: Extra Hours / PTO / Annual cover them; rest -> DED_UNDERTIME.\n"
            "dim = float(payslip.pfr_days_in_month or 30)\n"
            "wage = employee.wage or 0.0\n"
            "if wage <= 0 or not payslip:\n"
            "    result = 0.0\n"
            "else:\n"
            "    deduct_days = 0.0\n"
            "    for wd in payslip.worked_days_line_ids:\n"
            "        wet = wd.work_entry_type_id\n"
            "        code = ((wet.code or '') + ' ' + (wd.code or '')).strip().upper()\n"
            "        name = ((wet.name or '') + ' ' + (wd.name or '')).lower()\n"
            "        days = wd.number_of_days or 0.0\n"
            "        pct = wet.pfr_pay_percent if wet else 100.0\n"
            "        if 'OUT' in code or 'out of contract' in name or 'خارج' in name:\n"
            "            deduct_days += days\n"
            "        elif 'UNP' in code or 'SICKLEAVE0' in code or 'unpaid' in name or 'بدون' in name:\n"
            "            deduct_days += days\n"
            "        elif 'ABS' in code or 'absent' in name or 'غياب' in name or 'LATENESS' in code:\n"
            "            continue\n"
            "        elif pct < 100.0:\n"
            "            deduct_days += days * (1.0 - pct / 100.0)\n"
            "    result = round(max(0.0, dim - deduct_days) * wage / dim, 3)\n"),
    },
]


class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'

    def _pfr_ensure_rules(self):
        """Disabled: salary rules are managed manually per salary structure in Odoo UI."""
        return
