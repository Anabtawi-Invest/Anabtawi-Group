# -*- coding: utf-8 -*-
"""Amount column of the worked days: daily wage of the calendar month x days.

Odoo's own amount uses the wage of the payslip's employee record and the paid hours, which can be 0
(new employee record, hourly records, ...). The salary rules use the employee's monthly wage and a
calendar-month daily wage, so the column is aligned with them:

    paid line   : days x pay % x (wage / days in month)
    absent line : days x daily wage            (information: it is settled through the cash deduction)
    lateness    : hours x daily wage / 8       (information)
    unpaid / out of contract / overtime : 0

The value is applied in two places: Odoo's compute (so it follows later edits) and, explicitly, at the end of
Compute Sheet (so it never depends on how the compute is triggered).
"""
import calendar

from odoo import api, models


class HrPayslipWorkedDays(models.Model):
    _inherit = 'hr.payslip.worked_days'

    def _pfr_calendar_amount(self):
        """Amount of this line by the daily-wage calendar rule, or None if it cannot be computed."""
        self.ensure_one()
        slip = self.payslip_id
        if not slip or not slip.date_to or slip.state not in ('draft', 'verify'):
            return None
        wage = slip._pfr_wage()
        if wage <= 0:
            return None
        daily = wage / float(calendar.monthrange(slip.date_to.year, slip.date_to.month)[1])
        wet = self.work_entry_type_id
        kind = self.env['pfr.day.ledger'].classify_type(wet) if wet else 'PAID'
        code = (wet.code or '').upper() if wet else ''
        days = self.number_of_days or 0.0
        if kind in ('OUT', 'UNPAID', 'IGNORE'):
            return 0.0
        if kind == 'ABSENT':
            return round(days * daily, 3)
        if code in ('LATENESS', 'LAT', 'LATE'):
            return round((self.number_of_hours or 0.0) * daily / 8.0, 3)
        factor = wet._pfr_pay_factor() if wet else 1.0
        return round(days * factor * daily, 3)

    @api.depends('number_of_days', 'number_of_hours', 'work_entry_type_id',
                 'work_entry_type_id.pfr_pay_percent',
                 'payslip_id.date_to', 'payslip_id.version_id.wage', 'payslip_id.employee_id.wage')
    def _compute_amount(self):
        super()._compute_amount()
        for wd in self:
            amount = wd._pfr_calendar_amount()
            if amount is not None:
                wd.amount = amount

    def _pfr_apply_amount(self):
        """Write the calendar amount on the lines (used at the end of Compute Sheet)."""
        for wd in self:
            amount = wd._pfr_calendar_amount()
            if amount is not None and abs((wd.amount or 0.0) - amount) > 0.0005:
                wd.sudo().write({'amount': amount})
