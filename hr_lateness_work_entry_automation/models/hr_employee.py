from collections import defaultdict
from datetime import datetime, time, timedelta
import logging

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _lat_get_work_entry_source(self):
        self.ensure_one()
        version = self.version_id or self.current_version_id
        return (version.work_entry_source or "").strip() if version else ""

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

    def _lat_get_calendar_intervals_on_day(self, target_date, day_start, day_end):
        self.ensure_one()
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        calendar = (
            version.resource_calendar_id
            or self.resource_calendar_id
            or self.company_id.resource_calendar_id
        )
        if not calendar:
            return 0.0

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

        day_bounds = {day: self._lat_get_day_utc_bounds(day) for day in target_days}
        utc_start = min(start for start, _end in day_bounds.values())
        utc_end = max(end for _start, end in day_bounds.values())

        work_entry_source = self._lat_get_work_entry_source()
        planning_only_mode = work_entry_source == "planning"
        slot_states = ["published"] if planning_only_mode else ["draft", "published"]
        slots = self.env["planning.slot"].sudo().search([
            ("resource_id", "=", self.resource_id.id),
            ("state", "in", slot_states),
            ("start_datetime", "<", utc_end),
            ("end_datetime", ">", utc_start),
        ]) if self.resource_id else self.env["planning.slot"]

        attendances = self.env["hr.attendance"].sudo().search([
            ("employee_id", "=", self.id),
            ("check_out", "!=", False),
            ("check_in", "<", utc_end),
            ("check_out", ">", utc_start),
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
            len(slots),
            len(attendances),
            existing_lat_entries.ids,
        )
        entries_by_day = defaultdict(lambda: self.env["hr.work.entry"])
        for entry in existing_lat_entries:
            entries_by_day[entry.date] |= entry

        grace_hours = self._lat_grace_hours()
        for day in target_days:
            day_start, day_end = day_bounds[day]
            planning_intervals = []
            planned_source = "planning"
            for slot in slots:
                overlap_start = max(slot.start_datetime, day_start)
                overlap_end = min(slot.end_datetime, day_end)
                if overlap_end > overlap_start:
                    planning_intervals.append((overlap_start, overlap_end))

            if not planning_intervals and planning_only_mode:
                planned_source = "planning_published_only_no_slot"
            elif not planning_intervals:
                calendar_intervals = self._lat_get_calendar_intervals_on_day(day, day_start, day_end)
                if calendar_intervals:
                    planning_intervals = calendar_intervals
                    planned_source = "calendar_fallback"
                else:
                    planned_source = "none"

            planned_hours = 0.0
            planned_start = False
            planned_end = False
            for interval_start, interval_end in planning_intervals:
                planned_hours += (interval_end - interval_start).total_seconds() / 3600.0
                if not planned_start or interval_start < planned_start:
                    planned_start = interval_start
                if not planned_end or interval_end > planned_end:
                    planned_end = interval_end

            attendance_start = False
            attendance_end = False
            for attendance in attendances:
                if not attendance.check_in or not attendance.check_out:
                    continue
                if attendance.check_out <= attendance.check_in:
                    continue
                overlap_start = max(attendance.check_in, day_start)
                overlap_end = min(attendance.check_out, day_end)
                if overlap_end > overlap_start:
                    current_start = overlap_start
                    if not attendance_start or current_start < attendance_start:
                        attendance_start = current_start
                    if not attendance_end or overlap_end > attendance_end:
                        attendance_end = overlap_end

            late_check_in_hours = 0.0
            if planned_start and attendance_start and attendance_start > planned_start:
                late_check_in_hours = (attendance_start - planned_start).total_seconds() / 3600.0

            early_check_out_hours = 0.0
            if planned_end and attendance_end and planned_end > attendance_end:
                early_check_out_hours = (planned_end - attendance_end).total_seconds() / 3600.0

            # Threshold logic:
            # - <= grace: no lateness
            # - > grace: count the full lateness (including the first grace minutes)
            late_check_in_effective_hours = (
                late_check_in_hours if late_check_in_hours > grace_hours else 0.0
            )
            early_check_out_effective_hours = (
                early_check_out_hours if early_check_out_hours > grace_hours else 0.0
            )
            lateness_hours = max(late_check_in_hours + early_check_out_hours, 0.0)
            effective_lateness_hours = late_check_in_effective_hours + early_check_out_effective_hours
            should_have_lat = (
                bool(planned_start and planned_end and attendance_start and attendance_end)
                and effective_lateness_hours > 0.0
            )
            _logger.info(
                "[LAT] day_eval employee_id=%s employee=%s date=%s planned_start=%s planned_end=%s attendance_start=%s attendance_end=%s planned_hours=%.4f late_check_in=%.4f early_check_out=%.4f lateness=%.4f grace=%.4f late_check_in_effective=%.4f early_check_out_effective=%.4f effective_lateness=%.4f should_have_lat=%s existing_entries=%s",
                self.id,
                self.display_name,
                day,
                planned_start,
                planned_end,
                attendance_start,
                attendance_end,
                planned_hours,
                late_check_in_hours,
                early_check_out_hours,
                lateness_hours,
                grace_hours,
                late_check_in_effective_hours,
                early_check_out_effective_hours,
                effective_lateness_hours,
                should_have_lat,
                entries_by_day.get(day, self.env["hr.work.entry"]).ids,
            )
            _logger.warning(
                "[LAT TRACE2] employee=%s(%s) date=%s source=%s planned_start=%s planned_end=%s attendance_start=%s attendance_end=%s late_in=%.4f early_out=%.4f total=%.4f grace=%.4f late_in_effective=%.4f early_out_effective=%.4f effective=%.4f apply=%s",
                self.display_name,
                self.id,
                day,
                planned_source,
                planned_start,
                planned_end,
                attendance_start,
                attendance_end,
                late_check_in_hours,
                early_check_out_hours,
                lateness_hours,
                grace_hours,
                late_check_in_effective_hours,
                early_check_out_effective_hours,
                effective_lateness_hours,
                should_have_lat,
            )
            _logger.info(
                "[LAT] day_plan_source employee_id=%s employee=%s date=%s source=%s",
                self.id,
                self.display_name,
                day,
                planned_source,
            )
            self._lat_sync_work_entry_for_day(
                target_date=day,
                late_hours=effective_lateness_hours,
                should_have_lat=should_have_lat,
                lat_type=lat_type,
                existing_entries=entries_by_day.get(day, self.env["hr.work.entry"]),
            )
        _logger.info(
            "[LAT] employee_recompute_done employee_id=%s employee=%s",
            self.id,
            self.display_name,
        )

    def _lat_sync_work_entry_for_day(self, target_date, late_hours, should_have_lat, lat_type, existing_entries):
        self.ensure_one()
        existing_entries = existing_entries.sorted("id")
        if not should_have_lat:
            _logger.info(
                "[LAT] sync_action employee_id=%s employee=%s date=%s action=remove reason=no_lateness_above_grace existing_entries=%s",
                self.id,
                self.display_name,
                target_date,
                existing_entries.ids,
            )
            self._lat_remove_entries(existing_entries)
            return

        duration = min(round(late_hours, 4), 24.0)
        if duration <= 0.0:
            _logger.info(
                "[LAT] sync_action employee_id=%s employee=%s date=%s action=remove reason=non_positive_duration existing_entries=%s",
                self.id,
                self.display_name,
                target_date,
                existing_entries.ids,
            )
            self._lat_remove_entries(existing_entries)
            return

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
