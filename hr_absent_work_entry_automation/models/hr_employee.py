# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta

import logging
import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"
    @api.model
    def _get_lateness_grace_hours(self):
        return 15.0 / 60.0
    @api.model
    def _get_work_entry_type_by_code(self, code, fallback_name):
        work_entry_type = self.env["hr.work.entry.type"].search([("code", "=", code)], limit=1)
        if work_entry_type:
            return work_entry_type
        return self.env["hr.work.entry.type"].sudo().create({
            "name": fallback_name,
            "display_code": code,
            "code": code,
            "is_leave": False,
        })
    def _get_daily_work_entries(self, target_date, work_entry_type):
        self.ensure_one()
        return self.env["hr.work.entry"].sudo().search([
            ("employee_id", "=", self.id),
            ("date", "=", target_date),
            ("state", "!=", "cancelled"),
            ("work_entry_type_id", "=", work_entry_type.id),
        ])

    def _remove_daily_work_entries(self, target_date, work_entry_type):
        self.ensure_one()
        for entry in self._get_daily_work_entries(target_date, work_entry_type):
            if entry.state == "validated":
                entry.sudo().write({"state": "cancelled"})
            else:
                entry.sudo().unlink()

    def _upsert_daily_work_entry(self, target_date, work_entry_type, duration):
        self.ensure_one()
        duration = min(round(duration, 2), 24.0)
        if duration <= 0:
            self._remove_daily_work_entries(target_date, work_entry_type)
            return

        entries = self._get_daily_work_entries(target_date, work_entry_type).sorted("id")
        editable = entries.filtered(lambda e: e.state != "validated")
        if editable:
            keeper = editable[:1]
            keeper.sudo().write({"duration": duration})
            for entry in (entries - keeper):
                if entry.state == "validated":
                    entry.sudo().write({"state": "cancelled"})
                else:
                    entry.sudo().unlink()
            return

        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            _logger.info(
                "Work entry automation: skip employee=%s(%s) date=%s reason=no overlapping contract version type=%s",
                self.name,
                self.id,
                target_date,
                work_entry_type.code,
            )
            return

        self.env["hr.work.entry"].sudo().create({
            "employee_id": self.id,
            "version_id": version.id,
            "date": target_date,
            "duration": duration,
            "work_entry_type_id": work_entry_type.id,
            "company_id": self.company_id.id,
        })

    def _compute_lateness_hours_on_day(self, target_date):
        self.ensure_one()
        expected_hours = self._get_expected_hours_on_day(target_date)
        if expected_hours <= 0:
            return {
                "lateness_hours": 0.0,
                "expected_hours": expected_hours,
                "attended_hours": 0.0,
                "late_check_in_hours": 0.0,
                "early_check_out_hours": 0.0,
                "planned_start": False,
                "planned_end": False,
                "attendance_start": False,
                "attendance_end": False,
                "planned_source": "none",
            }
        attended_hours = self._get_attended_hours_on_day(target_date)
        planned_start, planned_end, planned_source = self._get_planned_bounds_on_day(target_date)
        attendance_start, attendance_end = self._get_attendance_bounds_on_day(target_date)

        late_check_in_hours = 0.0
        if planned_start and attendance_start and attendance_start > planned_start:
            late_check_in_hours = (attendance_start - planned_start).total_seconds() / 3600.0

        early_check_out_hours = 0.0
        if planned_end and attendance_end and planned_end > attendance_end:
            early_check_out_hours = (planned_end - attendance_end).total_seconds() / 3600.0

        lateness_hours = max(late_check_in_hours + early_check_out_hours, 0.0)
        return {
            "lateness_hours": lateness_hours,
            "expected_hours": expected_hours,
            "attended_hours": attended_hours,
            "late_check_in_hours": late_check_in_hours,
            "early_check_out_hours": early_check_out_hours,
            "planned_start": planned_start,
            "planned_end": planned_end,
            "attendance_start": attendance_start,
            "attendance_end": attendance_end,
            "planned_source": planned_source,
        }

    @api.model
    def _cron_create_absent_work_entries(self):
        """Daily cron: evaluate yesterday and create/update absent work entries."""
        target_date = fields.Date.context_today(self) - timedelta(days=1)
        self._create_absent_work_entries_for_day(target_date)

    @api.model
    def _create_absent_work_entries_for_day(self, target_date):
        target_date = fields.Date.to_date(target_date)
        _logger.info(
            "Absent automation: start processing date=%s",
            target_date,
        )
        absent_type = self.env.ref(
            "hr_absent_work_entry_automation.work_entry_type_absent",
            raise_if_not_found=False,
        )
        if not absent_type:
            absent_type = self.env["hr.work.entry.type"].search([("code", "=", "ABSENT")], limit=1)
        if not absent_type:
            _logger.warning(
                "Absent automation: skipped date=%s because ABSENT work entry type was not found",
                target_date,
            )
            return
        lateness_type = self._get_work_entry_type_by_code("LAT", "Lateness")

        employees = self.search([("active", "=", True)])
        _logger.info(
            "Absent automation: evaluating %s active employees for date=%s",
            len(employees),
            target_date,
        )
        for employee in employees:
            employee._apply_absence_for_day(target_date, absent_type, lateness_type)

    def _apply_absence_for_day(self, target_date, absent_type, lateness_type):
        self.ensure_one()
        expected_hours = self._get_expected_hours_on_day(target_date)
        if expected_hours <= 0:
            _logger.info(
                "Absent automation: skip employee=%s(%s) date=%s reason=no expected work hours",
                self.name,
                self.id,
                target_date,
            )
            self._remove_daily_work_entries(target_date, absent_type)
            self._remove_daily_work_entries(target_date, lateness_type)
            return
        has_checkin = self._has_checkin_on_day(target_date)
        if has_checkin:
            self._remove_daily_work_entries(target_date, absent_type)
            late_data = self._compute_lateness_hours_on_day(target_date)
            lateness_hours = late_data["lateness_hours"]
            grace = self._get_lateness_grace_hours()
            if lateness_hours > grace:
                self._upsert_daily_work_entry(target_date, lateness_type, lateness_hours)
                _logger.info(
                    "Lateness automation: upserted LAT employee=%s(%s) date=%s expected=%.2f attended=%.2f "
                    "planned_source=%s planned_start=%s planned_end=%s attendance_start=%s attendance_end=%s "
                    "late_check_in=%.2f early_check_out=%.2f lateness=%.2f grace=%.2f",
                    self.name,
                    self.id,
                    target_date,
                    late_data["expected_hours"],
                    late_data["attended_hours"],
                    late_data["planned_source"],
                    late_data["planned_start"],
                    late_data["planned_end"],
                    late_data["attendance_start"],
                    late_data["attendance_end"],
                    late_data["late_check_in_hours"],
                    late_data["early_check_out_hours"],
                    lateness_hours,
                    grace,
                )
            else:
                self._remove_daily_work_entries(target_date, lateness_type)
                _logger.info(
                    "Lateness automation: no LAT employee=%s(%s) date=%s expected=%.2f attended=%.2f "
                    "planned_source=%s planned_start=%s planned_end=%s attendance_start=%s attendance_end=%s "
                    "late_check_in=%.2f early_check_out=%.2f lateness=%.2f grace=%.2f",
                    self.name,
                    self.id,
                    target_date,
                    late_data["expected_hours"],
                    late_data["attended_hours"],
                    late_data["planned_source"],
                    late_data["planned_start"],
                    late_data["planned_end"],
                    late_data["attendance_start"],
                    late_data["attendance_end"],
                    late_data["late_check_in_hours"],
                    late_data["early_check_out_hours"],
                    lateness_hours,
                    grace,
                )
            _logger.info(
                "Absent automation: skip employee=%s(%s) date=%s reason=attendance check-in exists",
                self.name,
                self.id,
                target_date,
            )
            return
        if self._has_leave_work_entry_on_day(target_date):
            _logger.info(
                "Absent automation: skip employee=%s(%s) date=%s reason=leave work entry exists",
                self.name,
                self.id,
                target_date,
            )
            self._remove_daily_work_entries(target_date, absent_type)
            self._remove_daily_work_entries(target_date, lateness_type)
            return

        self._remove_daily_work_entries(target_date, lateness_type)
        self._upsert_daily_work_entry(target_date, absent_type, expected_hours)
        _logger.info(
            "Absent automation: created ABSENT work entry for employee=%s(%s) date=%s duration=%s",
            self.name,
            self.id,
            target_date,
            expected_hours,
        )

    def _has_expected_work_on_day(self, target_date):
        self.ensure_one()
        return self._get_expected_hours_on_day(target_date) > 0

    def _get_expected_hours_on_day(self, target_date):
        self.ensure_one()
        # Planning-only absence logic: ignore calendar working schedules.
        return self._get_planning_hours_on_day(target_date)

    def _get_day_utc_bounds(self, target_date):
        self.ensure_one()
        calendar = self.resource_calendar_id or self.company_id.resource_calendar_id
        tz_name = (calendar and calendar.tz) or self.tz or "UTC"
        employee_tz = pytz.timezone(tz_name)
        day_start_local = employee_tz.localize(datetime.combine(target_date, time.min))
        next_day_start_local = employee_tz.localize(datetime.combine(target_date + timedelta(days=1), time.min))
        day_start_utc = day_start_local.astimezone(pytz.utc).replace(tzinfo=None)
        next_day_start_utc = next_day_start_local.astimezone(pytz.utc).replace(tzinfo=None)
        return day_start_utc, next_day_start_utc, employee_tz

    def _get_planning_hours_on_day(self, target_date):
        self.ensure_one()
        slots = self._get_planning_intervals_on_day(target_date)
        total_hours = 0.0
        for overlap_start, overlap_end in slots:
            total_hours += (overlap_end - overlap_start).total_seconds() / 3600.0
        return total_hours

    def _get_planning_intervals_on_day(self, target_date):
        self.ensure_one()
        if "planning.slot" not in self.env or not self.resource_id:
            return []

        start_dt, end_dt, _employee_tz = self._get_day_utc_bounds(target_date)
        slots = self.env["planning.slot"].sudo().search([
            ("resource_id", "=", self.resource_id.id),
            ("start_datetime", "<", end_dt),
            ("end_datetime", ">", start_dt),
        ])

        intervals = []
        for slot in slots:
            overlap_start = max(slot.start_datetime, start_dt)
            overlap_end = min(slot.end_datetime, end_dt)
            if overlap_end > overlap_start:
                intervals.append((overlap_start, overlap_end))
        return intervals

    def _get_calendar_hours_on_day(self, target_date):
        self.ensure_one()
        intervals = self._get_calendar_intervals_on_day(target_date)
        total_hours = 0.0
        for interval_start, interval_end in intervals:
            total_hours += (interval_end - interval_start).total_seconds() / 3600.0
        return total_hours

    def _get_calendar_intervals_on_day(self, target_date):
        self.ensure_one()
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return []

        calendar = version.resource_calendar_id or self.resource_calendar_id or self.company_id.resource_calendar_id
        if not calendar:
            return []

        day_start_utc, day_end_utc, employee_tz = self._get_day_utc_bounds(target_date)
        day_start_utc_aware = pytz.utc.localize(day_start_utc)
        day_end_utc_aware = pytz.utc.localize(day_end_utc)

        resource = self.resource_id
        intervals_by_resource = calendar._attendance_intervals_batch(
            day_start_utc_aware,
            day_end_utc_aware,
            resources=resource,
            tz=employee_tz,
        )
        intervals = intervals_by_resource.get(resource.id if resource else False)
        if not intervals:
            return []

        values = []
        for interval_start, interval_end, _attendance in intervals._items:
            if interval_end > interval_start:
                values.append((
                    interval_start.astimezone(pytz.utc).replace(tzinfo=None),
                    interval_end.astimezone(pytz.utc).replace(tzinfo=None),
                ))
        return values

    def _get_planned_bounds_on_day(self, target_date):
        self.ensure_one()
        intervals = self._get_planning_intervals_on_day(target_date)
        source = "planning"
        if not intervals:
            intervals = self._get_calendar_intervals_on_day(target_date)
            source = "calendar"
        if not intervals:
            return False, False, "none"
        starts = [start for start, _end in intervals]
        ends = [end for _start, end in intervals]
        return min(starts), max(ends), source

    def _has_checkin_on_day(self, target_date):
        self.ensure_one()
        day_start, next_day_start, _employee_tz = self._get_day_utc_bounds(target_date)
        return bool(self.env["hr.attendance"].sudo().search_count([
            ("employee_id", "=", self.id),
            ("check_in", ">=", fields.Datetime.to_string(day_start)),
            ("check_in", "<", fields.Datetime.to_string(next_day_start)),
        ]))

    def _get_attended_hours_on_day(self, target_date):
        self.ensure_one()
        day_start, next_day_start, _employee_tz = self._get_day_utc_bounds(target_date)
        attendances = self.env["hr.attendance"].sudo().search([
            ("employee_id", "=", self.id),
            ("check_out", "!=", False),
            ("check_in", "<", fields.Datetime.to_string(next_day_start)),
            ("check_out", ">", fields.Datetime.to_string(day_start)),
        ])
        attended_hours = 0.0
        for attendance in attendances:
            overlap_start = max(attendance.check_in, day_start)
            overlap_end = min(attendance.check_out, next_day_start)
            if overlap_end > overlap_start:
                attended_hours += (overlap_end - overlap_start).total_seconds() / 3600.0
        return attended_hours

    def _get_attendance_bounds_on_day(self, target_date):
        self.ensure_one()
        day_start, next_day_start, _employee_tz = self._get_day_utc_bounds(target_date)
        attendances = self.env["hr.attendance"].sudo().search([
            ("employee_id", "=", self.id),
            ("check_out", "!=", False),
            ("check_in", "<", fields.Datetime.to_string(next_day_start)),
            ("check_out", ">", fields.Datetime.to_string(day_start)),
        ])
        starts = []
        ends = []
        for attendance in attendances:
            overlap_start = max(attendance.check_in, day_start)
            overlap_end = min(attendance.check_out, next_day_start)
            if overlap_end > overlap_start:
                starts.append(overlap_start)
                ends.append(overlap_end)
        if not starts or not ends:
            return False, False
        return min(starts), max(ends)

    def _has_leave_work_entry_on_day(self, target_date):
        self.ensure_one()
        return bool(self.env["hr.work.entry"].sudo().search_count([
            ("employee_id", "=", self.id),
            ("date", "=", target_date),
            ("state", "!=", "cancelled"),
            ("work_entry_type_id.is_leave", "=", True),
        ]))
