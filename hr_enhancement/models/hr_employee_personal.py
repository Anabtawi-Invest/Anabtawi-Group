# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, fields, models
from odoo.tools.float_utils import float_compare, float_round

_logger = logging.getLogger(__name__)

DAILY_CONVERSION_THRESHOLD = 8.0


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    ae_is_non_resident = fields.Boolean(
        string="Non-resident",
        groups="hr.group_hr_user",
        help="Indicates the employee should be classified as non-resident for statutory fields.",
    )
    ae_children_of_jordanian_mother = fields.Boolean(
        string="Children of Jordanian Mothers",
        groups="hr.group_hr_user",
    )
    ae_gaza_resident = fields.Boolean(
        string="Gaza Residents",
        groups="hr.group_hr_user",
    )
    daily_leave_hours_counter = fields.Float(
        string="Daily Leave Hours Counter",
        digits=(16, 2),
        default=0.0,
        help="Accumulated hours from the company daily leave type. "
             "Every 8 hours are converted into 1 annual leave day.",
        groups="hr_holidays.group_hr_holidays_user",
    )

    def _anabtawi_leave_type_field_name(self):
        Leave = self.env["hr.leave"]
        if "holiday_status_id" in Leave._fields:
            return "holiday_status_id"
        return "work_entry_type_id"

    def _anabtawi_convert_daily_leave_hours(self, source_leave=None):
        """Create 1 annual leave day for each full 8 hours on the counter."""
        Leave = self.env["hr.leave"].sudo()
        leave_type_field = self._anabtawi_leave_type_field_name()

        for employee in self:
            company = employee.company_id
            annual_type = company.daily_conversion_annual_leave_type_id
            daily_type = company.daily_leave_type_id
            if not annual_type or not daily_type:
                _logger.warning(
                    "Daily leave conversion skipped for employee %s: configure daily and annual leave types.",
                    employee.id,
                )
                continue

            request_date = (
                source_leave.request_date_from
                if source_leave and source_leave.request_date_from
                else fields.Date.context_today(employee)
            )
            safety = 0
            while (
                float_compare(
                    employee.daily_leave_hours_counter or 0.0,
                    DAILY_CONVERSION_THRESHOLD,
                    precision_digits=2,
                )
                >= 0
                and safety < 50
            ):
                safety += 1
                before = employee.daily_leave_hours_counter or 0.0
                note = _(
                    "Auto-created: 8 hours of %(daily)s converted to 1 annual leave day "
                    "(counter was %(before).2f hours). Source leave: %(source)s.",
                    daily=daily_type.display_name,
                    before=before,
                    source=source_leave.display_name if source_leave else _("N/A"),
                )
                vals = {
                    "employee_id": employee.id,
                    leave_type_field: annual_type.id,
                    "request_date_from": request_date,
                    "request_date_to": request_date,
                    "name": note,
                }
                try:
                    annual_leave = Leave.with_context(
                        skip_daily_leave_conversion=True,
                        skip_leave_fallback_logic=True,
                        leave_fast_create=True,
                        mail_create_nosubscribe=True,
                        tracking_disable=True,
                    ).create(vals)
                    annual_leave.with_context(
                        skip_daily_leave_conversion=True,
                        skip_leave_fallback_logic=True,
                        leave_fast_create=True,
                        mail_activity_automation_skip=True,
                    )._action_validate(check_state=False)
                    annual_leave.message_post(body=note)
                except Exception:
                    _logger.exception(
                        "Could not create annual leave for employee %s from daily leave conversion",
                        employee.id,
                    )
                    break

                employee.daily_leave_hours_counter = float_round(
                    before - DAILY_CONVERSION_THRESHOLD,
                    precision_digits=2,
                )
                _logger.info(
                    "Daily leave conversion: created annual leave for employee %s; counter %.2f -> %.2f",
                    employee.id,
                    before,
                    employee.daily_leave_hours_counter,
                )
                request_date = request_date + timedelta(days=1)
