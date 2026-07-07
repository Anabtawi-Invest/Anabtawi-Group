# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    second_manager_id = fields.Many2one(
        "res.users",
        string="Second Manager",
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        groups="hr_attendance.group_hr_attendance_officer",
        help="If set, this user is added as the second approver on overtime approval requests for this employee.",
    )
