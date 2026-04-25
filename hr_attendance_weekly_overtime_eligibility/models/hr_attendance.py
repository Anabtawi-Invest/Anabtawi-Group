from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


VALIDATION_MESSAGE = "Employee has not completed required weekly hours to qualify for overtime."


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

    def _check_weekly_overtime_eligibility(self):
        if any(not attendance.eligible_overtime for attendance in self):
            raise ValidationError(_(VALIDATION_MESSAGE))

    def action_approve_overtime(self):
        self._check_weekly_overtime_eligibility()
        return super().action_approve_overtime()
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


VALIDATION_MESSAGE = "Employee has not completed required weekly hours to qualify for overtime."


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

    def _check_weekly_overtime_eligibility(self):
        if any(not attendance.eligible_overtime for attendance in self):
            raise ValidationError(_(VALIDATION_MESSAGE))

    def action_approve_overtime(self):
        self._check_weekly_overtime_eligibility()
        return super().action_approve_overtime()
