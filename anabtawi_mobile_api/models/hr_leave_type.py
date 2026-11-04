from odoo import api, fields, models


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    employee_app_limit_enabled = fields.Boolean(
        string="Limit Employee App Request",
        help="When enabled, the Employee App warns the employee if the request exceeds the maximum amount.",
    )
    employee_app_max_request = fields.Float(
        string="Maximum Request",
        help="Maximum amount the employee can request in the Employee App without a warning. "
             "Use days when the duration type is days, or hours when the duration type is hours.",
    )
    employee_app_max_request_uom = fields.Char(
        string="Maximum Request Unit",
        compute="_compute_employee_app_max_request_uom",
    )

    @api.depends("request_unit")
    def _compute_employee_app_max_request_uom(self):
        for leave_type in self:
            leave_type.employee_app_max_request_uom = (
                "Hours" if leave_type.request_unit == "hour" else "Days"
            )
