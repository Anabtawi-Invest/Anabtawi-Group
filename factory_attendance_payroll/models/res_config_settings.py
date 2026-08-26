# -*- coding: utf-8 -*-
from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_overtime_calculation = fields.Boolean(
        related='company_id.enable_overtime_calculation',
        readonly=False,
        string="Enable Overtime Calculation",
        help="When unchecked, extra hours worked beyond the schedule are treated as unpaid hours and will not generate monthly overtime or affect payslips."
    )
