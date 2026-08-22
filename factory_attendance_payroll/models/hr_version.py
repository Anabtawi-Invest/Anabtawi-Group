# -*- coding: utf-8 -*-

from odoo import fields, models


class HrVersion(models.Model):
    _inherit = 'hr.version'

    is_payroll_manager = fields.Boolean(
        string="Manager",
        tracking=True,
        groups="hr_payroll.group_hr_payroll_user",
        help="When enabled, factory attendance reconciliation is skipped on payslips. "
             "Absent work entry automation still applies.",
    )
