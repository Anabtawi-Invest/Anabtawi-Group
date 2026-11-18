from odoo import api, fields, models


class HrAttendanceOvertimeLine(models.Model):
    _inherit = "hr.attendance.overtime.line"

    eligible_overtime = fields.Boolean(
        string="Eligible Overtime",
        compute="_compute_eligible_overtime",
    )

    @api.depends("employee_id")
    @api.depends_context("tz")
    def _compute_eligible_overtime(self):
        employees = self.mapped("employee_id")
        eligibility_map = employees._get_overtime_eligibility_map() if employees else {}
        for overtime_line in self:
            overtime_line.eligible_overtime = eligibility_map.get(
                overtime_line.employee_id.id, False
            )
