# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_overtime_calculation = fields.Boolean(
        string="Enable Overtime Calculation", default=True,
        help="When unchecked, extra hours do not generate overtime on payslips.")
    fap_annual_leave_type_id = fields.Many2one(
        'hr.leave.type', string="Reconciliation Annual Leave Type",
        domain="[('time_type', '=', 'leave'), ('company_id', 'in', [False, id])]",
        help="Annual leave type used for lateness deduction and termination settlement. "
             "Falls back to a name search ('Annual Leave') when empty.")


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_overtime_calculation = fields.Boolean(
        related='company_id.enable_overtime_calculation', readonly=False)
    fap_annual_leave_type_id = fields.Many2one(
        related='company_id.fap_annual_leave_type_id', readonly=False)
