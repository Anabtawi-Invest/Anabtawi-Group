# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'

    @api.model
    def _get_default_rule_ids(self):
        res = super(HrPayrollStructure, self)._get_default_rule_ids()
        res.extend([
            (0, 0, {
                'name': _('Health Insurance'),
                'sequence': 143,
                'code': 'HINSURN',
                'category_id': self.env.ref('hr_payroll.DED').id,
                'condition_select': 'python',
                'condition_python': "result = sum(employee.health_insurance_ids.mapped('monthly_contribution')) > 0",
                'amount_select': 'code',
                'amount_python_compute': """
payslipl_days = (payslip.date_to - payslip.date_from).days + 1
insurance = 0
for ins in employee.health_insurance_ids:
    if ins.manual_contribution > 0:
        insurance += ins.manual_contribution
    else:
        if ins.effective_date > payslip.date_from and ins.effective_date < payslip.date_to:
            valid_days = (payslip.date_to - ins.effective_date).days
            insurance += (ins.monthly_contribution / payslipl_days) * valid_days
        elif ins.effective_date <= payslip.date_from:
            insurance += ins.monthly_contribution
result =  -1 * insurance
                """,
            }),
        ])
        return res

    rule_ids = fields.One2many(default=_get_default_rule_ids)
