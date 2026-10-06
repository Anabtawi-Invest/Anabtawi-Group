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
            "# lateness + absent hours NOT covered by Extra Hours / Annual Leave (step 3)\n"
            "hours = round(payslip.undertime_cash_deduction_hours, 2)\n"
            "wage = employee.wage or 0.0\n"
            "result = min(hours * wage / 240.0, wage) if hours >= 0.01 else 0.0\n"),
    },
    {
        'code': 'ACTUAL', 'name': 'Actual Salary', 'category': 'hr_payroll.NET',
        'sequence': 90, 'appears_on_payslip': True, 'condition_select': 'none',
        'amount_python_compute': (
            "# calendar days - out of contract - unpaid - partial-pay types (e.g. Work Injury 7.5%).\n"
            "# ABSENT days are NOT cut here: Extra Hours cover them, any rest goes to DED_UNDERTIME.\n"
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

    @api.model_create_multi
    def create(self, vals_list):
        structures = super().create(vals_list)
        structures._pfr_ensure_rules()
        return structures

    def _pfr_ensure_rules(self):
        Rule = self.env['hr.salary.rule'].sudo()
        for struct in self.sudo():
            have = set(Rule.search([('struct_id', '=', struct.id)]).mapped('code'))
            for spec in RULES:
                if spec['code'] in have:
                    continue
                vals = {k: v for k, v in spec.items() if k != 'category'}
                vals.update(struct_id=struct.id, category_id=self.env.ref(spec['category']).id,
                            amount_select='code')
                Rule.create(vals)
