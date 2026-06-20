import logging
from collections import defaultdict
from datetime import timedelta

from odoo import models
from odoo.tools.date_utils import sum_intervals
from odoo.tools.float_utils import float_compare
from odoo.tools.intervals import Intervals

_logger = logging.getLogger(__name__)


class HrAttendanceOvertimeRule(models.Model):
    _inherit = "hr.attendance.overtime.rule"

    def _aer_target_attendance_id(self):
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("attendance_extra_hours_reason_log.trace_attendance_id", default="")
            .strip()
        )
        if not value:
            return 0
        try:
            return int(value)
        except ValueError:
            return 0

    @staticmethod
    def _aer_format_intervals(intervals):
        if not intervals:
            return []
        return [
            {
                "start": start,
                "end": stop,
                "meta_model": getattr(meta, "_name", str(type(meta))),
                "meta_ids": getattr(meta, "ids", []),
            }
            for start, stop, meta in intervals
        ]

    def _aer_should_trace(self, attendance_intervals):
        target_attendance_id = self._aer_target_attendance_id()
        if not target_attendance_id:
            return False, target_attendance_id
        for _start, _stop, attendance in attendance_intervals:
            if attendance.id == target_attendance_id:
                return True, target_attendance_id
        return False, target_attendance_id

    def _get_daterange_overtime_undertime_intervals_for_quantity_rule(self, start, stop, attendance_intervals, schedule):
        self.ensure_one()
        expected_duration = self.expected_hours
        attendances_interval_without_lunch = []
        intervals_attendance_by_attendance = defaultdict(Intervals)
        attendances = self.env["hr.attendance"]
        for (a_start, a_stop, attendance) in attendance_intervals:
            attendances += attendance
            intervals_attendance_by_attendance[attendance] = (
                (Intervals([(a_start, a_stop, self.env["resource.calendar"])]) - (schedule["lunch"] - schedule["leave"]))
                & Intervals([(start, stop, self.env["resource.calendar"])])
            )
            attendances_interval_without_lunch.extend(intervals_attendance_by_attendance[attendance]._items)

        if self.expected_hours_from_contract:
            period_schedule = (schedule["work"] - schedule["leave"]) & Intervals([(start, stop, self.env["resource.calendar"])])
            expected_duration = sum_intervals(period_schedule)
        else:
            period_schedule = Intervals([])

        actual_duration = sum_intervals(Intervals(attendances_interval_without_lunch))
        overtime_amount = actual_duration - expected_duration
        employee = attendances.employee_id
        company = self.company_id or employee.company_id

        should_trace, target_attendance_id = self._aer_should_trace(attendance_intervals)
        if should_trace:
            version = False
            calendar = False
            contract_id = False
            if employee:
                sample_attendance = attendances.sorted("check_in")[:1]
                version = (
                    employee.sudo()._get_version(sample_attendance.check_in.date())
                    if sample_attendance and hasattr(employee, "_get_version")
                    else employee.version_id
                )
                contract_id = version.id if version else False
                calendar = version.resource_calendar_id if version else employee.resource_calendar_id
            _logger.warning(
                (
                    "[attendance_extra_hours_reason_log][quantity_rule_trace] "
                    "target_attendance_id=%s rule_id=%s rule_name=%s "
                    "employee_id=%s contract_id=%s resource_calendar_id=%s "
                    "period_start=%s period_stop=%s "
                    "schedule_work=%s schedule_leave=%s schedule_lunch=%s "
                    "period_schedule=%s expected_duration=%s "
                    "attendances_interval_without_lunch=%s actual_duration=%s overtime_amount=%s"
                ),
                target_attendance_id,
                self.id,
                self.name,
                employee.id if employee else False,
                contract_id,
                calendar.id if calendar else False,
                start,
                stop,
                self._aer_format_intervals(schedule.get("work", Intervals([]))),
                self._aer_format_intervals(schedule.get("leave", Intervals([]))),
                self._aer_format_intervals(schedule.get("lunch", Intervals([]))),
                self._aer_format_intervals(period_schedule),
                expected_duration,
                self._aer_format_intervals(Intervals(attendances_interval_without_lunch)),
                actual_duration,
                overtime_amount,
            )

        if company.absence_management and float_compare(overtime_amount, -self.employee_tolerance, 5) == -1:
            last_attendance = sorted(intervals_attendance_by_attendance.keys(), key=lambda att: att.check_out)[-1]
            return {}, {last_attendance: [(overtime_amount, self)]}

        if float_compare(overtime_amount, self.employer_tolerance, 5) != 1:
            return {}, {}

        overtime_intervals = defaultdict(list)
        remaining_duration = expected_duration
        remanining_overtime_amount = overtime_amount
        for attendance in attendances.sorted("check_in"):
            for o_start, o_stop, _cal in intervals_attendance_by_attendance[attendance]:
                interval_duration = (o_stop - o_start).total_seconds() / 3600
                if remaining_duration >= interval_duration:
                    remaining_duration -= interval_duration
                    continue
                interval_overtime_duration = interval_duration
                if remaining_duration != 0:
                    interval_overtime_duration = interval_duration - remaining_duration
                new_start = o_stop - timedelta(hours=interval_overtime_duration)
                remaining_duration = 0
                overtime_intervals[attendance].append((new_start, o_stop, self))
                remanining_overtime_amount = remanining_overtime_amount - interval_overtime_duration
                if remanining_overtime_amount <= 0:
                    return overtime_intervals, {}
        return overtime_intervals, {}
