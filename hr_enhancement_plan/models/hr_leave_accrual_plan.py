# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrLeaveAccrualPlan(models.Model):
    _inherit = 'hr.leave.accrual.plan'

    milestone_reference = fields.Selection([
        ('allocation', 'Allocation start date'),
        ('contract', 'Employee contract start date'),
    ], string='Milestone relative to', default='allocation', required=True, export_string_translation=False,
        help='Reference date for milestone levels (e.g. "After 4 years"). '
             'Use "Employee contract start date" to base milestones on years of service.')
