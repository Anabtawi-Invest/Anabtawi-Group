from collections import defaultdict
from datetime import datetime, time, timedelta
import logging

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Complete list of Work Entry Type Codes (Display Codes & Payroll Codes) that represent
# Leaves, Holidays, Excused Time Off, and Special Allowances that must NOT generate lateness.
EXCUSED_LEAVE_WORK_ENTRY_CODES = [
    # Display Codes from Excel
    "GTO", "CTO", "HW", "STO", "PTO", "SIK", "ANU", "PHD", "BFV", "HIL",
    "FWS", "DIE", "MRD", "NPO", "PID", "HAJ", "MAM", "LDO", "TRV", "MKA", "BRK", "UNP",
    # Payroll Codes from Excel
    "LEAVE100", "LEAVE105", "WORK110", "LEAVE110", "LEAVE120", "SICKLEAVE0",
    "An_le", "un_paid",
    # General / standard leave codes
    "LEAVE", "SICK", "VAC", "ANNUAL", "UNPAID", "HOLIDAY",
]

ABSENT_WORK_ENTRY_CODES = ["ABS", "ABSENT"]


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.model
    def _lat_days_in_range(self, date_start, date_stop):
        start = fields.Date.to_date(date_start)
        stop = fields.Date.to_date(date_stop)
        if not start or not stop or stop < start:
            return []
        days = []
        current = start
        while current <= stop:
            days.append(current)
            current += timedelta(days=1)
        return days

    def generate_work_entries(self, date_start, date_stop, force=False):
        result = super().generate_work_entries(date_start, date_stop, force=force)
        days = self._lat_days_in_range(date_start, date_stop)
        if not days:
            return result
        recompute_map = self._lat_prepare_recompute_map()
        for employee in self.filtered("id"):
            recompute_map[employee.id].update(days)
        _logger.warning(
            "[LAT TRACE2] generate_work_entries_hook employee_ids=%s date_start=%s date_stop=%s force=%s days=%s",
            self.ids,
            date_start,
            date_stop,
            force,
            days,
        )
        self._lat_recompute_from_map(recompute_map)
        return result

    @api.model
    def _lat_grace_hours(self):
        return 15.0 / 60.0

    @api.model
    def _lat_float_is_zero(self, value, precision=1e-6):
        return abs(value) <= precision

    def _lat_get_work_entry_type(self):
        self.ensure_one()
        work_entry_type = self.env["hr.work.entry.type"].sudo().search([("code", "=", "LAT")], limit=1)
        if not work_entry_type:
            _logger.info(
                "[LAT] creating_work_entry_type code=LAT employee_id=%s employee=%s",
                self.id,
                self.display_name,
            )
            work_entry_type = self.env["hr.work.entry.type"].sudo().create({
                "name": "Lateness",
                "display_code": "LAT",
                "code": "LAT",
                "color": 2,
                "is_leave": False,
            })
        else:
            _logger.info(
                "[LAT] using_work_entry_type id=%s code=%s name=%s employee_id=%s employee=%s",
                work_entry_type.id,
                work_entry_type.code,
                work_entry_type.display_name,
                self.id,
                self.display_name,
            )
        return work_entry_type

    def _lat_get_timezone(self):
        self.ensure_one()
        calendar = self.resource_calendar_id or self.company_id.resource_calendar_id
        tz_name = (calendar and calendar.tz) or self.tz or "UTC"
        return pytz.timezone(tz_name)

    def _lat_get_day_utc_bounds(self, target_date):
        self.ensure_one()
        target_date = fields.Date.to_date(target_date)
        employee_tz = self._lat_get_timezone()
        day_start_local = employee_tz.localize(datetime.combine(target_date, time.min))
        next_day_local = employee_tz.localize(datetime.combine(target_date + timedelta(days=1), time.min))
        return (
            day_start_local.astimezone(pytz.utc).replace(tzinfo=None),
            next_day_local.astimezone(pytz.utc).replace(tzinfo=None),
        )

    def _lat_get_work_entry_source_on_day(self, target_date):
        self.ensure_one()
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if version and version.work_entry_source:
            return (version.work_entry_source or "").strip()
        if "planning.slot" in self.env and self.resource_id:
            slots_count = self.env["planning.slot"].sudo().search_count([
                ("resource_id", "=", self.resource_id.id),
            ])
            if slots_count > 0:
                return "planning"
        return "calendar"

    def _lat_has_approved_leave_on_day(self, target_date, day_start_utc, day_end_utc):
        self.ensure_one()
        # 1. Check hr.leave records with approved/validated state
        if "hr.leave" in self.env:
            leaves_count = self.env["hr.leave"].sudo().search_count([
                ("employee_id", "=", self.id),
                ("state", "in", ["validate", "validate1"]),
                ("date_from", "<", fields.Datetime.to_string(day_end_utc)),
                ("date_to", ">", fields.Datetime.to_string(day_start_utc)),
            ])
            if leaves_count > 0:
                return True

        # 2. Check hr.work.entry for all approved leave & time off types from Excel
        work_entries = self.env["hr.work.entry"].sudo().search([
            ("employee_id", "=", self.id),
            ("date", "=", target_date),
            ("state", "!=", "cancelled"),
        ])
        for we in work_entries:
            type_obj = we.work_entry_type_id
            if not type_obj:
                continue
            if type_obj.is_leave:
                return True
            code = (type_obj.code or "").strip()
            display_code = (getattr(type_obj, "display_code", False) or "").strip()
            if code in EXCUSED_LEAVE_WORK_ENTRY_CODES or display_code in EXCUSED_LEAVE_WORK_ENTRY_CODES:
                return True

        return False

    def _lat_has_absent_on_day(self, target_date):
        self.ensure_one()
        work_entries = self.env["hr.work.entry"].sudo().search([
            ("employee_id", "=", self.id),
            ("date", "=", target_date),
            ("state", "!=", "cancelled"),
        ])
        for we in work_entries:
            type_obj = we.work_entry_type_id
            if not type_obj:
                continue
            code = (type_obj.code or "").strip()
            display_code = (getattr(type_obj, "display_code", False) or "").strip()
            if code in ABSENT_WORK_ENTRY_CODES or display_code in ABSENT_WORK_ENTRY_CODES:
                return True
        return False

    def _lat_get_calendar_intervals_on_day(self, target_date, day_start, day_end):
        self.ensure_one()
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        calendar = (
            version.resource_calendar_id
            or self.resource_calendar_id
            or self.company_id.resource_calendar_id
        )
        if not calendar:
            return []

        start_aware = pytz.utc.localize(day_start)
        end_aware = pytz.utc.localize(day_end)
        resource = self.resource_id
        intervals_by_resource = calendar._attendance_intervals_batch(
            start_aware,
            end_aware,
            resources=resource,
            tz=self._lat_get_timezone(),
        )
        intervals = intervals_by_resource.get(resource.id if resource else False)
        if not intervals:
            return []

        normalized_intervals = []
        for interval_start, interval_end, _attendance in intervals._items:
            if interval_end > interval_start:
                normalized_intervals.append((
                    interval_start.astimezone(pytz.utc).replace(tzinfo=None),
                    interval_end.astimezone(pytz.utc).replace(tzinfo=None),
                ))
        return normalized_intervals

    def _lat_iter_days_from_interval(self, dt_start, dt_end):
        self.ensure_one()
        if not dt_start or not dt_end or dt_end <= dt_start:
            return set()
        employee_tz = self._lat_get_timezone()
        start_local = pytz.utc.localize(dt_start).astimezone(employee_tz)
        end_local = pytz.utc.localize(dt_end - timedelta(microseconds=1)).astimezone(employee_tz)
        current_date = start_local.date()
        end_date = end_local.date()
        days = set()
        while current_date <= end_date:
            days.add(current_date)
            current_date += timedelta(days=1)
        return days

    def _lat_prepare_recompute_map(self):
        return defaultdict(set)

    @api.model
    def _lat_collect_recompute_map_entry(self, recompute_map, employee, dt_start, dt_end):
        if not employee:
            return
        if not dt_start or not dt_end:
            return
        days = employee._lat_iter_days_from_interval(dt_start, dt_end)
        recompute_map[employee.id].update(days)
        _logger.info(
            "[LAT] collect_recompute employee_id=%s employee=%s dt_start=%s dt_end=%s days=%s",
            employee.id,
            employee.display_name,
            dt_start,
            dt_end,
            sorted(days),
        )

    @api.model
    def _lat_recompute_from_map(self, recompute_map):
        if not recompute_map:
            _logger.info("[LAT] recompute_skipped reason=empty_map")
            return
        employees = self.browse(list(recompute_map.keys())).exists()
        _logger.info(
            "[LAT] recompute_start employee_ids=%s day_map=%s",
            employees.ids,
            {employee_id: sorted(days) for employee_id, days in recompute_map.items()},
        )
        for employee in employees:
            employee._lat_recompute_days(recompute_map.get(employee.id, set()))
        _logger.info("[LAT] recompute_done employee_ids=%s", employees.ids)

    def _lat_recompute_days(self, target_days):
        self.ensure_one()
        target_days = sorted(fields.Date.to_date(day) for day in target_days if day)
        if not target_days:
            _logger.info(
                "[LAT] employee_recompute_skipped employee_id=%s employee=%s reason=no_target_days",
                self.id,
                self.display_name,
            )
            return
        _logger.info(
            "[LAT] employee_recompute_start employee_id=%s employee=%s target_days=%s",
            self.id,
            self.display_name,
            target_days,
        )
        lat_type = self._lat_get_work_entry_type()
        if not lat_type:
            _logger.warning(
                "[LAT] employee_recompute_skipped employee_id=%s employee=%s reason=no_lat_type",
                self.id,
                self.display_name,
            )
            return

        employee_tz = self._lat_get_timezone()
        day_bounds = {day: self._lat_get_day_utc_bounds(day) for day in target_days}
        min_day_start = min(start for start, _end in day_bounds.values())
        max_day_end = max(end for _start, end in day_bounds.values())

        # Fetch planning slots within range (extended by 24h for overnight shifts)
        all_slots = self.env["planning.slot"].sudo().search([
            ("resource_id", "=", self.resource_id.id),
            ("state", "in", ["draft", "published"]),
            ("start_datetime", "<", max_day_end + timedelta(hours=24)),
            ("end_datetime", ">", min_day_start - timedelta(hours=24)),
        ]) if self.resource_id else self.env["planning.slot"]

        # Fetch attendances within range (extended by 24h for overnight attendances)
        all_attendances = self.env["hr.attendance"].sudo().search([
            ("employee_id", "=", self.id),
            ("check_in", "<", max_day_end + timedelta(hours=24)),
            ("check_in", ">=", min_day_start - timedelta(hours=24)),
        ])

        existing_lat_entries = self.env["hr.work.entry"].sudo().search([
            ("employee_id", "=", self.id),
            ("date", "in", target_days),
            ("work_entry_type_id", "=", lat_type.id),
            ("state", "!=", "cancelled"),
        ])
        _logger.info(
            "[LAT] employee_sources employee_id=%s employee=%s slots=%s attendances=%s existing_lat_entries=%s",
            self.id,
            self.display_name,
            len(all_slots),
            len(all_attendances),
            existing_lat_entries.ids,
        )
        entries_by_day = defaultdict(lambda: self.env["hr.work.entry"])
        for entry in existing_lat_entries:
            entries_by_day[entry.date] |= entry

        grace_hours = self._lat_grace_hours()

        for day in target_days:
            day_start, day_end = day_bounds[day]
            existing_day_entries = entries_by_day.get(day, self.env["hr.work.entry"])

            # 1. Check if day is an Approved Leave / Time Off (All excused codes from Excel)
            if self._lat_has_approved_leave_on_day(day, day_start, day_end):
                _logger.info(
                    "[LAT] day_eval employee_id=%s date=%s skipped=approved_leave_or_excused_work_entry",
                    self.id,
                    day,
                )
                self._lat_sync_work_entry_for_day(
                    target_date=day,
                    late_hours=0.0,
                    should_have_lat=False,
                    lat_type=lat_type,
                    existing_entries=existing_day_entries,
                )
                continue

            # 2. Check if day is marked as Absent (ABS / ABSENT)
            if self._lat_has_absent_on_day(day):
                _logger.info(
                    "[LAT] day_eval employee_id=%s date=%s skipped=marked_as_absent",
                    self.id,
                    day,
                )
                self._lat_sync_work_entry_for_day(
                    target_date=day,
                    late_hours=0.0,
                    should_have_lat=False,
                    lat_type=lat_type,
                    existing_entries=existing_day_entries,
                )
                continue

            work_entry_source = self._lat_get_work_entry_source_on_day(day)
            total_lateness_hours = 0.0
            has_attended_shift = False

            if work_entry_source == "planning":
                # Find all planning slots starting on this date in employee local timezone
                day_slots = []
                for slot in all_slots:
                    slot_start_local = pytz.utc.localize(slot.start_datetime).astimezone(employee_tz)
                    if slot_start_local.date() == day:
                        day_slots.append(slot)

                if not day_slots:
                    # Unscheduled Day / Day Off: DO NOT fallback to calendar!
                    _logger.info(
                        "[LAT] day_eval employee_id=%s date=%s skipped=unscheduled_planning_day_off",
                        self.id,
                        day,
                    )
                    self._lat_sync_work_entry_for_day(
                        target_date=day,
                        late_hours=0.0,
                        should_have_lat=False,
                        lat_type=lat_type,
                        existing_entries=existing_day_entries,
                    )
                    continue

                for slot in day_slots:
                    shift_start = slot.start_datetime
                    shift_end = slot.end_datetime

                    # Match attendances for this specific shift window
                    # Window: from 4 hours before shift start up to shift end
                    shift_attendances = all_attendances.filtered(
                        lambda att: att.check_in and att.check_in >= (shift_start - timedelta(hours=4)) and att.check_in <= shift_end
                    )

                    if not shift_attendances:
                        # Employee did not attend the scheduled shift -> Absence, not Lateness
                        _logger.info(
                            "[LAT] shift_eval employee_id=%s date=%s slot_id=%s no_attendance_found=absence",
                            self.id,
                            day,
                            slot.id,
                        )
                        continue

                    att_start = min(att.check_in for att in shift_attendances)
                    closed_attendances = shift_attendances.filtered(
                        lambda att: att.check_out and att.check_out > att.check_in
                    )
                    att_end = max(att.check_out for att in closed_attendances) if closed_attendances else False

                    has_attended_shift = True

                    # 1. Late arrival (Check-in lateness)
                    late_in = 0.0
                    if att_start > shift_start:
                        late_in = (att_start - shift_start).total_seconds() / 3600.0

                    # 2. Early departure (Check-out lateness across whole shift, including overnight)
                    early_out = 0.0
                    if att_end and att_end < shift_end:
                        early_out = (shift_end - att_end).total_seconds() / 3600.0

                    shift_lateness = late_in + early_out
                    total_lateness_hours += shift_lateness
                    _logger.info(
                        "[LAT] shift_eval employee_id=%s date=%s slot_id=%s shift_start=%s shift_end=%s att_start=%s att_end=%s late_in=%.4f early_out=%.4f shift_lateness=%.4f",
                        self.id,
                        day,
                        slot.id,
                        shift_start,
                        shift_end,
                        att_start,
                        att_end,
                        late_in,
                        early_out,
                        shift_lateness,
                    )

                should_have_lat = has_attended_shift and (total_lateness_hours > grace_hours)

            else:
                # Working Schedule (Calendar) Fallback for non-planning employees
                calendar_intervals = self._lat_get_calendar_intervals_on_day(day, day_start, day_end)
                if not calendar_intervals:
                    # Non-working day in calendar (Weekend / Day Off)
                    should_have_lat = False
                else:
                    cal_start = min(start for start, end in calendar_intervals)
                    cal_end = max(end for start, end in calendar_intervals)

                    day_attendances = all_attendances.filtered(
                        lambda att: att.check_in and att.check_in >= (day_start - timedelta(hours=2)) and att.check_in < day_end
                    )

                    if not day_attendances:
                        should_have_lat = False
                    else:
                        att_start = min(att.check_in for att in day_attendances)
                        closed_attendances = day_attendances.filtered(
                            lambda att: att.check_out and att.check_out > att.check_in
                        )
                        att_end = max(att.check_out for att in closed_attendances) if closed_attendances else False

                        late_in = 0.0
                        if att_start > cal_start:
                            late_in = (att_start - cal_start).total_seconds() / 3600.0

                        early_out = 0.0
                        if att_end and att_end < cal_end:
                            early_out = (cal_end - att_end).total_seconds() / 3600.0

                        total_lateness_hours = late_in + early_out
                        should_have_lat = bool(att_start) and (total_lateness_hours > grace_hours)

            _logger.info(
                "[LAT] day_summary employee_id=%s date=%s source=%s total_lateness=%.4f grace=%.4f should_have_lat=%s",
                self.id,
                day,
                work_entry_source,
                total_lateness_hours,
                grace_hours,
                should_have_lat,
            )

            self._lat_sync_work_entry_for_day(
                target_date=day,
                late_hours=total_lateness_hours if should_have_lat else 0.0,
                should_have_lat=should_have_lat,
                lat_type=lat_type,
                existing_entries=existing_day_entries,
            )

        _logger.info(
            "[LAT] employee_recompute_done employee_id=%s employee=%s",
            self.id,
            self.display_name,
        )

    def _lat_sync_work_entry_for_day(self, target_date, late_hours, should_have_lat, lat_type, existing_entries):
        self.ensure_one()
        existing_entries = existing_entries.sorted("id")
        if not should_have_lat or late_hours <= 0.0:
            _logger.info(
                "[LAT] sync_action employee_id=%s employee=%s date=%s action=remove reason=not_applicable existing_entries=%s",
                self.id,
                self.display_name,
                target_date,
                existing_entries.ids,
            )
            self._lat_remove_entries(existing_entries)
            return

        duration = min(round(late_hours, 4), 24.0)
        editable_entries = existing_entries.filtered(lambda entry: entry.state != "validated")
        if editable_entries:
            keeper = editable_entries[0]
            keeper.sudo().write({"duration": duration})
            self._lat_remove_entries(existing_entries - keeper)
            _logger.info(
                "[LAT] sync_action employee_id=%s employee=%s date=%s action=update duration=%.4f keeper=%s removed_duplicates=%s",
                self.id,
                self.display_name,
                target_date,
                duration,
                keeper.id,
                (existing_entries - keeper).ids,
            )
            return

        if existing_entries:
            _logger.info(
                "[LAT] sync_action employee_id=%s employee=%s date=%s action=cleanup_validated_before_create existing_entries=%s",
                self.id,
                self.display_name,
                target_date,
                existing_entries.ids,
            )
            self._lat_remove_entries(existing_entries)

        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            _logger.warning(
                "[LAT] sync_skipped employee_id=%s employee=%s date=%s reason=no_contract_version duration=%.4f",
                self.id,
                self.display_name,
                target_date,
                duration,
            )
            return

        work_entry = self.env["hr.work.entry"].sudo().create({
            "employee_id": self.id,
            "version_id": version.id,
            "date": target_date,
            "duration": duration,
            "work_entry_type_id": lat_type.id,
            "company_id": self.company_id.id,
        })
        _logger.info(
            "[LAT] sync_action employee_id=%s employee=%s date=%s action=create duration=%.4f work_entry_id=%s version_id=%s",
            self.id,
            self.display_name,
            target_date,
            duration,
            work_entry.id,
            version.id,
        )

    def _lat_remove_entries(self, entries):
        for entry in entries:
            if entry.state == "validated":
                _logger.info(
                    "[LAT] remove_entry entry_id=%s date=%s employee_id=%s action=cancel reason=validated",
                    entry.id,
                    entry.date,
                    entry.employee_id.id,
                )
                entry.sudo().write({"state": "cancelled"})
            else:
                _logger.info(
                    "[LAT] remove_entry entry_id=%s date=%s employee_id=%s action=unlink state=%s",
                    entry.id,
                    entry.date,
                    entry.employee_id.id,
                    entry.state,
                )
                entry.sudo().unlink()
