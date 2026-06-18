from datetime import timedelta

import pytz

from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals_list = [
            self._prepare_normalized_attendance_vals(vals)
            for vals in vals_list
        ]
        return super().create(normalized_vals_list)

    def write(self, vals):
        if not {"employee_id", "check_in", "check_out"} & set(vals):
            return super().write(vals)

        if len(self) == 1:
            normalized_vals = self._prepare_normalized_attendance_vals(
                vals,
                current_attendance=self,
            )
            return super().write(normalized_vals)

        result = True
        for attendance in self:
            normalized_vals = attendance._prepare_normalized_attendance_vals(
                vals,
                current_attendance=attendance,
            )
            result = super(HrAttendance, attendance).write(normalized_vals) and result
        return result

    def _prepare_normalized_attendance_vals(self, vals, current_attendance=None):
        normalized_vals = dict(vals)
        employee = self._resolve_employee_for_vals(normalized_vals, current_attendance)
        if not employee or not employee.resource_calendar_id:
            return normalized_vals

        check_in_dt = fields.Datetime.to_datetime(normalized_vals.get("check_in"))
        check_out_dt = fields.Datetime.to_datetime(normalized_vals.get("check_out"))
        if current_attendance and not check_in_dt:
            check_in_dt = current_attendance.check_in
        if current_attendance and not check_out_dt:
            check_out_dt = current_attendance.check_out

        if "check_in" in normalized_vals and check_in_dt:
            check_in_dt = self._normalize_check_in_time(employee, check_in_dt)
            normalized_vals["check_in"] = check_in_dt

        if "check_out" in normalized_vals and check_out_dt:
            reference_check_in = check_in_dt or (
                current_attendance and current_attendance.check_in
            )
            check_out_dt = self._normalize_check_out_time(
                employee,
                check_out_dt,
                check_in_dt=reference_check_in,
            )
            normalized_vals["check_out"] = check_out_dt

        return normalized_vals

    def _resolve_employee_for_vals(self, vals, current_attendance=None):
        employee_id = vals.get("employee_id")
        if employee_id:
            return self.env["hr.employee"].browse(employee_id).exists()
        if current_attendance:
            return current_attendance.employee_id
        return self._default_employee() or self.env.user.employee_id

    def _normalize_check_in_time(self, employee, check_in_dt):
        tz = self._get_employee_timezone(employee)
        day_bounds = self._get_employee_schedule_day_bounds(
            employee=employee,
            reference_dt=check_in_dt,
            check_in_dt=check_in_dt,
        )
        if not day_bounds:
            return check_in_dt

        day_start, _day_end = day_bounds
        check_in_local = self._convert_utc_naive_to_tz(check_in_dt, tz)
        if check_in_local >= day_start:
            return check_in_dt
        return day_start.astimezone(pytz.UTC).replace(tzinfo=None)

    def _normalize_check_out_time(self, employee, check_out_dt, check_in_dt=None):
        del employee, check_in_dt
        # Disable schedule-based clipping for check-out.
        return check_out_dt

    def _get_employee_schedule_day_bounds(self, employee, reference_dt, check_in_dt=None):
        if not employee.resource_calendar_id:
            return False

        tz = self._get_employee_timezone(employee)
        pivot_dt = check_in_dt or reference_dt
        pivot_local = self._convert_utc_naive_to_tz(pivot_dt, tz)
        day_start_local = pivot_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end_local = day_start_local + timedelta(days=1)
        interval_items = self._get_employee_work_intervals(
            employee,
            day_start_local,
            day_end_local,
        )
        if not interval_items:
            return False

        day_first_start = min(item[0] for item in interval_items)
        day_last_end = max(item[1] for item in interval_items)
        return day_first_start, day_last_end

    def _get_employee_work_intervals(self, employee, interval_start_local, interval_end_local):
        calendar = employee.resource_calendar_id
        interval_start_utc = interval_start_local.astimezone(pytz.UTC)
        interval_end_utc = interval_end_local.astimezone(pytz.UTC)

        intervals_map = calendar._attendance_intervals_batch(
            interval_start_utc,
            interval_end_utc,
            resources=employee.resource_id,
            lunch=False,
        )
        employee_intervals = intervals_map.get(employee.resource_id.id)
        if not employee_intervals:
            return []
        return sorted(employee_intervals._items, key=lambda item: item[0])

    def _get_employee_timezone(self, employee):
        timezone_name = employee._get_tz() or employee.tz or employee.resource_id.tz or "UTC"
        try:
            return pytz.timezone(timezone_name)
        except Exception:
            return pytz.UTC

    def _convert_utc_naive_to_tz(self, naive_utc_dt, tz):
        if naive_utc_dt.tzinfo:
            return naive_utc_dt.astimezone(tz)
        return pytz.UTC.localize(naive_utc_dt).astimezone(tz)

