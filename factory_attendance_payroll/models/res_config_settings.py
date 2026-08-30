# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_overtime_calculation = fields.Boolean(
        string="Enable Overtime Calculation",
        default=True,
        help="When unchecked, extra hours worked by employees will not generate overtime on payslips."
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_overtime_calculation = fields.Boolean(
        related='company_id.enable_overtime_calculation',
        readonly=False,
        string="Factory Overtime Calculation"
    )
