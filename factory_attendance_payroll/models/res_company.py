# -*- coding: utf-8 -*-
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_overtime_calculation = fields.Boolean(
        string="Enable Overtime Calculation",
        default=True,
        help="When unchecked, extra hours worked beyond the schedule are treated as unpaid hours and will not generate monthly overtime or affect payslips."
    )
