import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

from pytz import UTC, UnknownTimeZoneError, timezone

from odoo import api, fields, models
from odoo.tools.float_utils import float_compare


_logger = logging.getLogger(__name__)

CONFIG_PARAM_KEY = "hr_attendance_weekly_overtime_eligibility.required_weekly_hours"


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    weekly_worked_hours = fields.Float(
        string="Weekly Worked Hours",
        compute="_compute_weekly_worked_hours",
    )

    def _get_attendance_timezone(self):
        self.ensure_one()
        return (
            self.user_id.tz
            or self.resource_calendar_id.tz
            or self.env.user.tz
            or "UTC"
        )

    @api.model
    def _get_current_week_utc_bounds(self, tz_name):
        today = fields.Date.context_today(self)
        week_start = today - timedelta(days=today.weekday())
        next_week_start = week_start + timedelta(days=7)
        try:
            tz = timezone(tz_name or "UTC")
        except UnknownTimeZoneError:
            tz = UTC

        week_start_utc = tz.localize(datetime.combine(week_start, time.min)).astimezone(UTC)
        next_week_start_utc = tz.localize(datetime.combine(next_week_start, time.min)).astimezone(UTC)
        return week_start_utc.replace(tzinfo=None), next_week_start_utc.replace(tzinfo=None)

    @api.model
    def _get_required_weekly_hours(self):
        value = self.env["ir.config_parameter"].sudo().get_param(CONFIG_PARAM_KEY, default="0.0")
        return float(value or 0.0)

    def _get_overtime_eligibility_map(self):
        required_weekly_hours = self._get_required_weekly_hours()
        return {
            employee.id: float_compare(
                employee.weekly_worked_hours, required_weekly_hours, precision_digits=2
            )
            >= 0
            for employee in self
        }

    @api.depends_context("tz")
    def _compute_weekly_worked_hours(self):
        hours_by_employee = defaultdict(float)
        employees_by_tz = defaultdict(lambda: self.env["hr.employee"])

        for employee in self:
            employees_by_tz[employee._get_attendance_timezone()] |= employee

        attendance_model = self.env["hr.attendance"].sudo()
        for tz_name, employees in employees_by_tz.items():
            week_start_utc, next_week_start_utc = self._get_current_week_utc_bounds(tz_name)
            _logger.info(
                "[weekly_overtime_eligibility] Computing weekly worked hours for timezone=%s, "
                "week_start_utc=%s, week_end_utc=%s, employee_ids=%s",
                tz_name,
                week_start_utc,
                next_week_start_utc,
                employees.ids,
            )
            attendance_data = attendance_model._read_group(
                [
                    ("employee_id", "in", employees.ids),
                    ("check_in", ">=", week_start_utc),
                    ("check_in", "<", next_week_start_utc),
                ],
                ["employee_id"],
                ["worked_hours:sum"],
            )
            for employee, worked_hours in attendance_data:
                hours_by_employee[employee.id] = worked_hours
                _logger.info(
                    "[weekly_overtime_eligibility] Weekly worked hours aggregated for employee_id=%s, "
                    "employee_name=%s, timezone=%s, week_start_utc=%s, week_end_utc=%s, worked_hours=%s",
                    employee.id,
                    employee.display_name,
                    tz_name,
                    week_start_utc,
                    next_week_start_utc,
                    worked_hours,
                )

        for employee in self:
            employee.weekly_worked_hours = hours_by_employee[employee.id]
            _logger.info(
                "[weekly_overtime_eligibility] Final weekly worked hours set for employee_id=%s, "
                "employee_name=%s, timezone=%s, weekly_worked_hours=%s",
                employee.id,
                employee.display_name,
                employee._get_attendance_timezone(),
                employee.weekly_worked_hours,
            )
