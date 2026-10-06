# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_overtime_calculation = fields.Boolean(
        related='company_id.enable_overtime_calculation',
        readonly=False,
        string="Enable Overtime Calculation"
    )
    recon_annual_leave_type_id = fields.Many2one(
        related='company_id.recon_annual_leave_type_id',
        readonly=False,
        string="Reconciliation Annual Leave Type"
    )
