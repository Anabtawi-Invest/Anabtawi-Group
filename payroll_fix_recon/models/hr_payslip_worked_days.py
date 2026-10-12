# -*- coding: utf-8 -*-
"""Amount column of the worked days: daily wage of the calendar month x days.

Odoo's own amount uses the wage of the payslip's employee record and the paid hours, which can be 0
(new employee record, hourly records, ...). The salary rules use the employee's monthly wage and a
calendar-month daily wage, so the column is aligned with them:

    paid line   : days x pay % x (wage / days in month)
    absent line : days x daily wage            (information: it is settled through the cash deduction)
    lateness    : hours x daily wage / 8       (information)
    unpaid / out of contract / overtime : 0
"""
import calendar

from odoo import api, models


class HrPayslipWorkedDays(models.Model):
    _inherit = 'hr.payslip.worked_days'

    @api.depends('number_of_days', 'number_of_hours', 'work_entry_type_id',
                 'work_entry_type_id.pfr_pay_percent',
                 'payslip_id.date_to', 'payslip_id.version_id.wage', 'payslip_id.employee_id.wage')
    def _compute_amount(self):
        super()._compute_amount()
        ledger = self.env['pfr.day.ledger']
        for wd in self:
            slip = wd.payslip_id
            if not slip or not slip.date_to or slip.state not in ('draft', 'verify'):
                continue
            wage = slip._pfr_wage()
            if wage <= 0:
                continue
            daily = wage / float(calendar.monthrange(slip.date_to.year, slip.date_to.month)[1])
            wet = wd.work_entry_type_id
            kind = ledger.classify_type(wet) if wet else 'PAID'
            code = (wet.code or '').upper() if wet else ''
            if kind in ('OUT', 'UNPAID', 'IGNORE'):
                wd.amount = 0.0
            elif kind == 'ABSENT':
                wd.amount = round((wd.number_of_days or 0.0) * daily, 3)
            elif code in ('LATENESS', 'LAT', 'LATE'):
                wd.amount = round((wd.number_of_hours or 0.0) * daily / 8.0, 3)
            else:
                wd.amount = round((wd.number_of_days or 0.0) * wet._pfr_pay_factor() * daily, 3) if wet \
                    else round((wd.number_of_days or 0.0) * daily, 3)
