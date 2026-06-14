from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

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
            work_entry_type = self.env["hr.work.entry.type"].sudo().create({
                "name": "Lateness",
                "display_code": "LAT",
                "code": "LAT",
                "color": 2,
                "is_leave": False,
            })
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
        recompute_map[employee.id].update(employee._lat_iter_days_from_interval(dt_start, dt_end))

    @api.model
    def _lat_recompute_from_map(self, recompute_map):
        if not recompute_map:
            return
        employees = self.browse(list(recompute_map.keys())).exists()
        for employee in employees:
            employee._lat_recompute_days(recompute_map.get(employee.id, set()))

    def _lat_recompute_days(self, target_days):
        self.ensure_one()
        target_days = sorted(fields.Date.to_date(day) for day in target_days if day)
        if not target_days:
            return
        lat_type = self._lat_get_work_entry_type()
        if not lat_type:
            return

        day_bounds = {day: self._lat_get_day_utc_bounds(day) for day in target_days}
        utc_start = min(start for start, _end in day_bounds.values())
        utc_end = max(end for _start, end in day_bounds.values())

        slots = self.env["planning.slot"].sudo().search([
            ("resource_id", "=", self.resource_id.id),
            ("state", "=", "published"),
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
        entries_by_day = defaultdict(lambda: self.env["hr.work.entry"])
        for entry in existing_lat_entries:
            entries_by_day[entry.date] |= entry

        grace_hours = self._lat_grace_hours()
        for day in target_days:
            day_start, day_end = day_bounds[day]
            planned_hours = 0.0
            for slot in slots:
                overlap_start = max(slot.start_datetime, day_start)
                overlap_end = min(slot.end_datetime, day_end)
                if overlap_end > overlap_start:
                    planned_hours += (overlap_end - overlap_start).total_seconds() / 3600.0

            attended_hours = 0.0
            for attendance in attendances:
                if not attendance.check_in or not attendance.check_out:
                    continue
                if attendance.check_out <= attendance.check_in:
                    continue
                overlap_start = max(attendance.check_in, day_start)
                overlap_end = min(attendance.check_out, day_end)
                if overlap_end > overlap_start:
                    attended_hours += (overlap_end - overlap_start).total_seconds() / 3600.0

            lateness_hours = max(planned_hours - attended_hours, 0.0)
            should_have_lat = (
                not self._lat_float_is_zero(planned_hours)
                and lateness_hours > grace_hours
            )
            self._lat_sync_work_entry_for_day(
                target_date=day,
                late_hours=lateness_hours,
                should_have_lat=should_have_lat,
                lat_type=lat_type,
                existing_entries=entries_by_day.get(day, self.env["hr.work.entry"]),
            )

    def _lat_sync_work_entry_for_day(self, target_date, late_hours, should_have_lat, lat_type, existing_entries):
        self.ensure_one()
        existing_entries = existing_entries.sorted("id")
        if not should_have_lat:
            self._lat_remove_entries(existing_entries)
            return

        duration = min(round(late_hours, 4), 24.0)
        if duration <= 0.0:
            self._lat_remove_entries(existing_entries)
            return

        editable_entries = existing_entries.filtered(lambda entry: entry.state != "validated")
        if editable_entries:
            keeper = editable_entries[0]
            keeper.sudo().write({"duration": duration})
            self._lat_remove_entries(existing_entries - keeper)
            return

        if existing_entries:
            self._lat_remove_entries(existing_entries)

        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return

        self.env["hr.work.entry"].sudo().create({
            "employee_id": self.id,
            "version_id": version.id,
            "date": target_date,
            "duration": duration,
            "work_entry_type_id": lat_type.id,
            "company_id": self.company_id.id,
        })

    def _lat_remove_entries(self, entries):
        for entry in entries:
            if entry.state == "validated":
                entry.sudo().write({"state": "cancelled"})
            else:
                entry.sudo().unlink()
