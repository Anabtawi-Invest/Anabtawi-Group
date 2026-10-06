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
        'code': 'DED_UNDERTIME', 'name': 'Excess Undertime Deduction', 'category': 'hr_payroll.DED',
        'sequence': 70, 'appears_on_payslip': True, 'condition_select': 'python',
        'condition_python': "result = round(payslip.undertime_cash_deduction_hours, 2) >= 0.01\n",
        'amount_python_compute': (
            "hours = round(payslip.undertime_cash_deduction_hours, 2)\n"
            "wage = (payslip.version_id.wage if payslip.version_id else 0.0) or payslip.employee_id.wage\n"
            "result = -(hours * wage / 240.0) if hours >= 0.01 else 0.0\n"),
    },
    {
        'code': 'ACTUAL', 'name': 'Actual Salary', 'category': 'hr_payroll.NET',
        'sequence': 90, 'appears_on_payslip': True, 'condition_select': 'none',
        'amount_python_compute': (
            "# paid days x daily wage; unpaid leave / out-of-contract days are not paid, and lateness\n"
            "# (incl. ABSENT days) is deducted once through DED_UNDERTIME\n"
            "wage = (payslip.version_id.wage if payslip.version_id else 0.0) or payslip.employee_id.wage\n"
            "if wage <= 0:\n"
            "    result = 0.0\n"
            "elif not payslip.worked_days_line_ids:\n"
            "    result = wage\n"
            "else:\n"
            "    result = round(payslip.pfr_paid_days * wage / payslip.pfr_days_in_month, 3)\n"),
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
