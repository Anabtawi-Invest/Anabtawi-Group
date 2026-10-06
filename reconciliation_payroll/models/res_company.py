# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_overtime_calculation = fields.Boolean(
        string="Enable Overtime Calculation",
        default=True,
        help="When unchecked, extra hours worked beyond the schedule are treated as unpaid hours and will not generate overtime or affect payslips."
    )
    recon_annual_leave_type_id = fields.Many2one(
        'hr.leave.type',
        string="Reconciliation Annual Leave Type",
        domain="[('time_type', '=', 'leave'), ('company_id', 'in', [False, id])]",
        help="Time off type used for lateness deductions from Annual Leave and balance evaluation in termination clearance."
    )
