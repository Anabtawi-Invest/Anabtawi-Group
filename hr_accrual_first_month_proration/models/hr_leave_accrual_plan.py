# -*- coding: utf-8 -*-
from odoo import fields, models


class HrLeaveAccrualPlan(models.Model):
    _inherit = 'hr.leave.accrual.plan'

    prorate_first_month = fields.Boolean(
        string='Prorate first month',
        default=False,
        help='Prorate the first monthly accrual by calendar days: '
             'monthly rate x eligible days / days in the joining month '
             '(joining day included). Applied once per allocation.',
    )

    prorate_last_month = fields.Boolean(
        string='Prorate last month',
        default=False,
        help='When the employee has a contract end date, prorate the accrual of the '
             'leaving month by calendar days (leaving day included) and accrue nothing afterwards.',
    )
