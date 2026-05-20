from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from pytz import timezone, utc

from odoo import models
from odoo.tools.intervals import Intervals


class HrVersion(models.Model):
    _inherit = "hr.version"

    def _get_overtime_intervals(self, start_dt, end_dt):
        overtime_intervals = super()._get_overtime_intervals(start_dt, end_dt)
        normalized_intervals = {}
        for resource_id, intervals in overtime_intervals.items():
            singleton_payload_intervals = []
            for start, end, overtime in intervals:
                for overtime_line in overtime:
                    singleton_payload_intervals.append((start, end, overtime_line))
            # Return raw tuples to avoid Intervals normalization merging
            # same-boundary overtime lines back into multi-record payloads.
            normalized_intervals[resource_id] = singleton_payload_intervals
        return normalized_intervals

    def _get_attendance_intervals(self, start_dt, end_dt):
        start_naive = start_dt.replace(tzinfo=None)
        end_naive = end_dt.replace(tzinfo=None)
        attendance_based_contracts = self.filtered_domain([("work_entry_source", "=", "attendance")])
        search_domain = [
            ("employee_id", "in", attendance_based_contracts.employee_id.ids),
            ("check_in", "<", end_naive),
            ("check_out", ">", start_naive),
        ]
        resource_ids = attendance_based_contracts.employee_id.resource_id.ids
        attendances = (
            self.env["hr.attendance"].sudo().search(search_domain)
            if attendance_based_contracts
            else self.env["hr.attendance"]
        )
        intervals = defaultdict(list)
        calendar_by_employee = {}
        leaves = {}
        lunches = {}
        employee_by_calendar = defaultdict(lambda: self.env["hr.employee"])
        for version in self:
            calendar = version.resource_calendar_id
            if calendar and not calendar.flexible_hours:
                calendar_by_employee[version.employee_id] = calendar
                employee_by_calendar[calendar] += version.employee_id
        for calendar, employees in employee_by_calendar.items():
            leaves |= calendar._leave_intervals_batch(start_dt, end_dt, resources=employees.resource_id)
            lunches |= calendar._attendance_intervals_batch(
                start_dt, end_dt, resources=employees.resource_id, lunch=True
            )
        for attendance in attendances:
            resource = attendance.employee_id.resource_id
            tz = timezone(attendance.employee_id.tz or resource.tz)
            check_in_tz = attendance.check_in.astimezone(tz)
            check_out_tz = attendance.check_out.astimezone(tz)
            if attendance.overtime_status == "refused":
                check_out_tz -= timedelta(hours=attendance.validated_overtime_hours)

            resource_lunch = lunches.get(attendance.employee_id.resource_id.id, Intervals([]))
            resource_leave = leaves.get(attendance.employee_id.resource_id.id, Intervals([]))
            real_lunch_intervals = resource_lunch - resource_leave
            attendance_intervals = (
                Intervals([(check_in_tz, check_out_tz, attendance)]) - real_lunch_intervals
            )
            for interval in attendance_intervals:
                intervals[resource.id].append(
                    (max(start_dt, interval[0]), min(end_dt, interval[1]), attendance)
                )

        mapped_intervals = {r: Intervals(intervals[r], keep_distinct=True) for r in resource_ids}
        mapped_intervals.update(super()._get_attendance_intervals(start_dt, end_dt))

        working_schedule_versions = self.filtered(lambda v: v.work_entry_source == "calendar")
        if working_schedule_versions:
            working_schedule_search_domain = [
                ("employee_id", "in", working_schedule_versions.employee_id.ids),
                ("check_in", "<", end_naive),
                ("check_out", ">", start_naive),
            ]
            working_schedule_attendances = self.env["hr.attendance"].sudo().search(
                working_schedule_search_domain
            )

            for attendance in working_schedule_attendances:
                if not attendance.overtime_hours or not attendance.employee_id.version_id.overtime_from_attendance:
                    continue
                version = working_schedule_versions.filtered(
                    lambda v: v.employee_id == attendance.employee_id
                    and v.contract_date_start <= attendance.check_out.date()
                    and (not v.contract_date_end or v.contract_date_end >= attendance.check_in.date())
                )
                if not version:
                    continue
                version = version[0]
                tz = timezone(
                    version.resource_calendar_id.tz
                    or attendance.employee_id.tz
                    or attendance.employee_id.resource_id.tz
                )
                check_in_tz = attendance.check_in.astimezone(tz)
                schedule_intervals = mapped_intervals[version.employee_id.resource_id.id]
                if schedule_intervals:
                    items = list(schedule_intervals)
                    matching_interval = next(
                        (interval for interval in items if interval[0].date() == check_in_tz.date()),
                        None,
                    )
                    if matching_interval:
                        start, stop, recs = matching_interval
                        if check_in_tz < start:
                            idx = items.index(matching_interval)
                            items[idx] = (check_in_tz, stop, recs)
                            mapped_intervals[version.employee_id.resource_id.id] = Intervals(
                                items, keep_distinct=True
                            )

        overtime_intervals = {r: Intervals(keep_distinct=True) for r in mapped_intervals}
        overtime_contracts = self.filtered(
            lambda c: c.work_entry_source == "attendance" or c.overtime_from_attendance
        )
        overtime_intervals.update(overtime_contracts._get_overtime_intervals(start_dt, end_dt))

        work_entry_overtime_intervals = defaultdict(list)
        for r, intervals in overtime_intervals.items():
            for start, end, overtime in intervals:
                approved_overtimes = overtime.filtered(
                    lambda ot: ot.status == "approved" and ot.rule_ids.mapped("work_entry_type_id")
                )
                if not approved_overtimes:
                    continue
                # Keep overtime payloads singleton to match enterprise expectations.
                for approved_overtime in approved_overtimes:
                    work_entry_overtime_intervals[r].append((start, end, approved_overtime))

        return {
            r: (mapped_intervals[r] - overtime_intervals[r])
            | Intervals(work_entry_overtime_intervals[r], keep_distinct=True)
            for r in mapped_intervals
        }

    def _get_real_attendance_work_entry_vals(self, intervals):
        self.ensure_one()
        non_attendance_intervals = [
            interval
            for interval in intervals
            if interval[2]._name not in ["hr.attendance", "hr.attendance.overtime.line"]
        ]
        attendance_intervals = [
            interval
            for interval in intervals
            if interval[2]._name in ["hr.attendance", "hr.attendance.overtime.line"]
        ]
        if attendance_intervals:
            default_overtime_type = self.env.ref("hr_work_entry.work_entry_type_overtime")
            attendance_work_entry_type = self.env.ref("hr_work_entry.work_entry_type_attendance")
        vals = super()._get_real_attendance_work_entry_vals(non_attendance_intervals)

        employee = self.employee_id
        for interval in attendance_intervals:
            if interval[2]._name == "hr.attendance":
                work_entry_type = attendance_work_entry_type
                vals += [
                    dict(
                        [
                            ("name", "%s: %s" % (work_entry_type.name, employee.name)),
                            ("date_start", interval[0].astimezone(utc).replace(tzinfo=None)),
                            ("date_stop", interval[1].astimezone(utc).replace(tzinfo=None)),
                            ("work_entry_type_id", work_entry_type.id),
                            ("employee_id", employee.id),
                            ("version_id", self.id),
                            ("company_id", self.company_id.id),
                        ]
                        + self._get_more_vals_attendance_interval(interval)
                    )
                ]
                continue

            for overtime_line in interval[2]:
                if overtime_line.status != "approved":
                    continue
                overtime_mode = self.ruleset_id.rate_combination_mode
                triggered_rule_work_entry_types = (
                    overtime_line.rule_ids.mapped("work_entry_type_id") or default_overtime_type
                )
                date_start = interval[0].astimezone(utc).replace(tzinfo=None)
                date_stop = date_start + relativedelta(hours=overtime_line.manual_duration)
                overtime_interval = (interval[0], interval[1], overtime_line)

                if overtime_mode == "max" or len(triggered_rule_work_entry_types) == 1:
                    work_entry_type = max(
                        triggered_rule_work_entry_types, key=lambda w: w.amount_rate
                    )
                    vals += [
                        dict(
                            [
                                ("name", "%s: %s" % (work_entry_type.name, employee.name)),
                                ("date_start", date_start),
                                ("date_stop", date_stop),
                                ("work_entry_type_id", work_entry_type.id),
                                ("employee_id", employee.id),
                                ("version_id", self.id),
                                ("company_id", self.company_id.id),
                            ]
                            + self._get_more_vals_attendance_interval(overtime_interval)
                        )
                    ]
                else:
                    for triggered_rule in overtime_line.rule_ids.filtered("work_entry_type_id"):
                        vals += [
                            dict(
                                [
                                    ("name", "%s: %s" % (triggered_rule.work_entry_type_id.name, employee.name)),
                                    ("date_start", date_start),
                                    ("date_stop", date_stop),
                                    ("work_entry_type_id", triggered_rule.work_entry_type_id.id),
                                    ("employee_id", employee.id),
                                    ("version_id", self.id),
                                    ("company_id", self.company_id.id),
                                ]
                                + self._get_more_vals_attendance_interval(overtime_interval)
                            )
                        ]
        return vals
