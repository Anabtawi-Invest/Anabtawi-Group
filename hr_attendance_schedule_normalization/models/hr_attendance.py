from datetime import timedelta
from functools import reduce
from math import gcd

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
        shift_interval = self._get_employee_schedule_interval(
            employee=employee,
            reference_dt=check_in_dt,
            check_in_dt=check_in_dt,
        )
        if not shift_interval:
            return check_in_dt

        shift_start, shift_end = shift_interval
        check_in_local = self._convert_utc_naive_to_tz(check_in_dt, tz)
        if check_in_local <= shift_start:
            return check_in_dt

        rounding_minutes = self._get_schedule_rounding_minutes(employee.resource_calendar_id)
        normalized_local = self._round_datetime_up(
            check_in_local,
            anchor_dt=shift_start,
            rounding_minutes=rounding_minutes,
        )
        normalized_local = min(normalized_local, shift_end)
        return normalized_local.astimezone(pytz.UTC).replace(tzinfo=None)

    def _normalize_check_out_time(self, employee, check_out_dt, check_in_dt=None):
        tz = self._get_employee_timezone(employee)
        shift_interval = self._get_employee_schedule_interval(
            employee=employee,
            reference_dt=check_out_dt,
            check_in_dt=check_in_dt,
        )
        if not shift_interval:
            return check_out_dt

        _shift_start, shift_end = shift_interval
        check_out_local = self._convert_utc_naive_to_tz(check_out_dt, tz)
        if check_out_local <= shift_end:
            return check_out_dt

        normalized_check_out = shift_end.astimezone(pytz.UTC).replace(tzinfo=None)
        if check_in_dt and normalized_check_out < check_in_dt:
            return check_in_dt
        return normalized_check_out

    def _get_employee_schedule_interval(self, employee, reference_dt, check_in_dt=None):
        if not employee.resource_calendar_id:
            return False

        tz = self._get_employee_timezone(employee)
        pivot_dt = check_in_dt or reference_dt
        pivot_local = self._convert_utc_naive_to_tz(pivot_dt, tz)
        interval_items = self._get_employee_work_intervals(employee, pivot_local)
        if not interval_items:
            return False

        containing_index = self._find_containing_interval_index(interval_items, pivot_local)
        if containing_index is None:
            if check_in_dt:
                return False
            reference_local = self._convert_utc_naive_to_tz(reference_dt, tz)
            previous_intervals = [item for item in interval_items if item[0] <= reference_local]
            if not previous_intervals:
                return False
            latest_interval = previous_intervals[-1]
            return latest_interval[0], latest_interval[1]

        return self._expand_contiguous_shift(interval_items, containing_index)

    def _get_employee_work_intervals(self, employee, pivot_local_dt):
        calendar = employee.resource_calendar_id
        interval_start_local = pivot_local_dt - timedelta(days=1)
        interval_end_local = pivot_local_dt + timedelta(days=2)
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

    def _find_containing_interval_index(self, interval_items, dt_localized):
        for index, (start_dt, end_dt, _attendance_line) in enumerate(interval_items):
            if start_dt <= dt_localized <= end_dt:
                return index
        return None

    def _expand_contiguous_shift(self, interval_items, initial_index):
        shift_start, shift_end, _line = interval_items[initial_index]
        # Overnight shifts are commonly split into adjacent intervals across midnight.
        # Merge contiguous intervals to treat them as one logical shift.
        max_allowed_gap = timedelta(seconds=1)

        previous_index = initial_index - 1
        while previous_index >= 0:
            previous_start, previous_end, _line = interval_items[previous_index]
            if shift_start - previous_end > max_allowed_gap:
                break
            shift_start = previous_start
            previous_index -= 1

        next_index = initial_index + 1
        while next_index < len(interval_items):
            next_start, next_end, _line = interval_items[next_index]
            if next_start - shift_end > max_allowed_gap:
                break
            shift_end = next_end
            next_index += 1

        return shift_start, shift_end

    def _get_schedule_rounding_minutes(self, calendar):
        work_attendance_lines = calendar.attendance_ids.filtered(
            lambda line: not line.display_type and line.day_period != "lunch"
        )
        minute_marks = []
        for line in work_attendance_lines:
            minute_marks.append(int(round(line.hour_from * 60)))
            minute_marks.append(int(round(line.hour_to * 60)))
        minute_marks = [minute_mark for minute_mark in minute_marks if minute_mark > 0]
        if not minute_marks:
            return 60
        # Derive a stable rounding step (e.g. 15/30/60 min) from schedule boundaries.
        return reduce(gcd, minute_marks) or 60

    def _round_datetime_up(self, target_dt, anchor_dt, rounding_minutes):
        rounding_seconds = max(1, int(rounding_minutes)) * 60
        delta_seconds = (target_dt - anchor_dt).total_seconds()
        if delta_seconds <= 0:
            return anchor_dt
        rounded_steps = int((delta_seconds + rounding_seconds - 1) // rounding_seconds)
        return anchor_dt + timedelta(seconds=rounded_steps * rounding_seconds)

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
