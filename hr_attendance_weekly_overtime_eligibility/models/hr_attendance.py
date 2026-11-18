from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    eligible_overtime = fields.Boolean(
        string="Eligible Overtime",
        compute="_compute_eligible_overtime",
    )

    @api.depends("employee_id")
    @api.depends_context("tz")
    def _compute_eligible_overtime(self):
        employees = self.mapped("employee_id")
        eligibility_map = employees._get_overtime_eligibility_map() if employees else {}
        for attendance in self:
            attendance.eligible_overtime = eligibility_map.get(attendance.employee_id.id, False)
