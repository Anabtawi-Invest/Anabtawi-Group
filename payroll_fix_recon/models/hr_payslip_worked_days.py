# -*- coding: utf-8 -*-
"""Keeps the Amount column of the worked days on the daily-wage calendar rule when Odoo recomputes it.
The calculation itself lives on hr.payslip (_pfr_line_calendar_amount); Compute Sheet also writes it
explicitly, so the column does not depend on this compute being triggered."""
from odoo import api, models


class HrPayslipWorkedDays(models.Model):
    _inherit = 'hr.payslip.worked_days'

    @api.depends('number_of_days', 'number_of_hours', 'work_entry_type_id',
                 'work_entry_type_id.pfr_pay_percent',
                 'payslip_id.date_to', 'payslip_id.version_id.wage', 'payslip_id.employee_id.wage')
    def _compute_amount(self):
        super()._compute_amount()
        for wd in self:
            if not wd.payslip_id:
                continue
            amount = wd.payslip_id._pfr_line_calendar_amount(wd)
            if amount is not None:
                wd.amount = amount
