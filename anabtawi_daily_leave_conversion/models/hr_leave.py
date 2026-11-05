import logging

from odoo import _, api, fields, models
from odoo.tools.float_utils import float_compare, float_is_zero, float_round

_logger = logging.getLogger(__name__)

DAILY_CONVERSION_THRESHOLD = 8.0


class HrLeave(models.Model):
    _inherit = "hr.leave"

    daily_conversion_hours_applied = fields.Float(
        string="Daily Conversion Hours Applied",
        digits=(16, 2),
        copy=False,
        help="Hours from this leave that were already added to the employee daily leave counter.",
    )

    def _anabtawi_leave_type_field(self):
        if "holiday_status_id" in self._fields:
            return "holiday_status_id"
        return "work_entry_type_id"

    def _anabtawi_leave_type(self):
        self.ensure_one()
        return self[self._anabtawi_leave_type_field()]

    def _anabtawi_leave_hours(self):
        self.ensure_one()
        hours = self.number_of_hours or 0.0
        if not float_is_zero(hours, precision_digits=2):
            return float_round(hours, precision_digits=2)
        calendar = self.resource_calendar_id or self.employee_id.resource_calendar_id
        hours_per_day = calendar.hours_per_day if calendar and calendar.hours_per_day else 8.0
        return float_round((self.number_of_days or 0.0) * hours_per_day, precision_digits=2)

    def _anabtawi_is_configured_daily_leave(self):
        self.ensure_one()
        company = self.employee_company_id or self.employee_id.company_id or self.env.company
        daily_type = company.daily_leave_type_id
        leave_type = self._anabtawi_leave_type()
        return bool(daily_type and leave_type and leave_type.id == daily_type.id)

    def _action_validate(self, check_state=True):
        res = super()._action_validate(check_state=check_state)
        if self.env.context.get("skip_daily_leave_conversion"):
            return res
        self.filtered(
            lambda leave: leave.state == "validate"
            and float_is_zero(leave.daily_conversion_hours_applied, precision_digits=2)
        )._anabtawi_apply_daily_leave_conversion()
        return res

    def action_refuse(self):
        to_reverse = self.filtered(
            lambda leave: leave.state == "validate"
            and not float_is_zero(leave.daily_conversion_hours_applied, precision_digits=2)
        )
        res = super().action_refuse()
        to_reverse._anabtawi_reverse_daily_leave_conversion()
        return res

    def _force_cancel(self, reason=None, msg_subtype="mail.mt_comment", notify_responsibles=True):
        to_reverse = self.filtered(
            lambda leave: leave.state == "validate"
            and not float_is_zero(leave.daily_conversion_hours_applied, precision_digits=2)
        )
        res = super()._force_cancel(
            reason=reason,
            msg_subtype=msg_subtype,
            notify_responsibles=notify_responsibles,
        )
        to_reverse._anabtawi_reverse_daily_leave_conversion()
        return res

    def _anabtawi_apply_daily_leave_conversion(self):
        for leave in self:
            if not leave._anabtawi_is_configured_daily_leave() or not leave.employee_id:
                continue
            hours = leave._anabtawi_leave_hours()
            if float_compare(hours, 0.0, precision_digits=2) <= 0:
                continue
            employee = leave.employee_id.sudo()
            employee.daily_leave_hours_counter = float_round(
                (employee.daily_leave_hours_counter or 0.0) + hours,
                precision_digits=2,
            )
            leave.daily_conversion_hours_applied = hours
            _logger.info(
                "Daily leave conversion: added %.2f hours from leave %s for employee %s; counter=%.2f",
                hours,
                leave.id,
                employee.id,
                employee.daily_leave_hours_counter,
            )
            employee._anabtawi_convert_daily_leave_hours(source_leave=leave)

    def _anabtawi_reverse_daily_leave_conversion(self):
        for leave in self:
            hours = leave.daily_conversion_hours_applied or 0.0
            if float_is_zero(hours, precision_digits=2) or not leave.employee_id:
                continue
            employee = leave.employee_id.sudo()
            employee.daily_leave_hours_counter = float_round(
                max((employee.daily_leave_hours_counter or 0.0) - hours, 0.0),
                precision_digits=2,
            )
            leave.daily_conversion_hours_applied = 0.0
            _logger.info(
                "Daily leave conversion: removed %.2f hours from leave %s for employee %s; counter=%.2f",
                hours,
                leave.id,
                employee.id,
                employee.daily_leave_hours_counter,
            )
