import logging

from odoo import models

_logger = logging.getLogger(__name__)
LOG_TARGET_EMPLOYEE_ID = 2344


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    @staticmethod
    def _should_log_for_employee(employee):
        return bool(employee and employee.id == LOG_TARGET_EMPLOYEE_ID)

    @staticmethod
    def _get_overlap_hours(range_start, range_stop, intervals):
        total = 0.0
        for start, stop in intervals:
            overlap_start = max(range_start, start)
            overlap_stop = min(range_stop, stop)
            if overlap_stop > overlap_start:
                total += (overlap_stop - overlap_start).total_seconds() / 3600.0
        return total

    def _get_public_holiday_intervals(self, attendance, calendar, log_enabled=False):
        leave_model = self.env["resource.calendar.leaves"].sudo()
        resource = attendance.employee_id.resource_id
        matching_leaves = leave_model.search(
            [
                ("calendar_id", "=", calendar.id),
                ("date_from", "<", attendance.check_out),
                ("date_to", ">", attendance.check_in),
                "|",
                ("resource_id", "=", False),
                ("resource_id", "=", resource.id),
            ]
        )
        all_overlapping_leaves = leave_model.search(
            [
                ("date_from", "<", attendance.check_out),
                ("date_to", ">", attendance.check_in),
                "|",
                ("resource_id", "=", False),
                ("resource_id", "=", resource.id),
            ]
        )
        selected_leaves = matching_leaves or all_overlapping_leaves
        selection_mode = "matching_calendar" if matching_leaves else "all_overlapping_fallback"

        intervals = []
        for leave in selected_leaves:
            if leave.date_to > leave.date_from:
                intervals.append((leave.date_from, leave.date_to))
        if log_enabled:
            _logger.warning(
                "[planning_direct_overtime] holiday_scan attendance_id=%s employee_id=%s "
                "calendar_id=%s calendar_name=%s selection_mode=%s selected_leave_ids=%s selected_leave_rows=%s "
                "matching_leave_ids=%s matching_leave_rows=%s "
                "all_overlapping_leave_ids=%s all_overlapping_leave_rows=%s",
                attendance.id,
                attendance.employee_id.id,
                calendar.id,
                calendar.name,
                selection_mode,
                selected_leaves.ids,
                [
                    {
                        "id": leave.id,
                        "calendar_id": leave.calendar_id.id,
                        "calendar_name": leave.calendar_id.name,
                        "resource_id": leave.resource_id.id if leave.resource_id else False,
                        "resource_name": leave.resource_id.display_name if leave.resource_id else False,
                        "date_from": leave.date_from,
                        "date_to": leave.date_to,
                        "work_entry_type_id": leave.work_entry_type_id.id if leave.work_entry_type_id else False,
                        "work_entry_type_name": leave.work_entry_type_id.name if leave.work_entry_type_id else False,
                    }
                    for leave in selected_leaves
                ],
                matching_leaves.ids,
                [
                    {
                        "id": leave.id,
                        "calendar_id": leave.calendar_id.id,
                        "calendar_name": leave.calendar_id.name,
                        "resource_id": leave.resource_id.id if leave.resource_id else False,
                        "resource_name": leave.resource_id.display_name if leave.resource_id else False,
                        "date_from": leave.date_from,
                        "date_to": leave.date_to,
                        "work_entry_type_id": leave.work_entry_type_id.id if leave.work_entry_type_id else False,
                        "work_entry_type_name": leave.work_entry_type_id.name if leave.work_entry_type_id else False,
                    }
                    for leave in matching_leaves
                ],
                all_overlapping_leaves.ids,
                [
                    {
                        "id": leave.id,
                        "calendar_id": leave.calendar_id.id,
                        "calendar_name": leave.calendar_id.name,
                        "resource_id": leave.resource_id.id if leave.resource_id else False,
                        "resource_name": leave.resource_id.display_name if leave.resource_id else False,
                        "date_from": leave.date_from,
                        "date_to": leave.date_to,
                        "work_entry_type_id": leave.work_entry_type_id.id if leave.work_entry_type_id else False,
                        "work_entry_type_name": leave.work_entry_type_id.name if leave.work_entry_type_id else False,
                    }
                    for leave in all_overlapping_leaves
                ],
            )
        return selected_leaves, intervals

    def _update_overtime(self, attendance_domain=None):
        result = super()._update_overtime(attendance_domain=attendance_domain)
        impacted_attendances = (
            self | self.env["hr.attendance"].search(attendance_domain or [])
        ).filtered(lambda att: att.check_in and att.check_out and att.employee_id)
        target_attendance_ids = impacted_attendances.filtered(
            lambda att: self._should_log_for_employee(att.employee_id)
        ).ids
        if target_attendance_ids:
            _logger.warning(
                "[planning_direct_overtime] trigger=_update_overtime domain=%s attendance_ids=%s",
                attendance_domain,
                target_attendance_ids,
            )
        self._apply_planning_direct_overtime(impacted_attendances)
        return result

    def _apply_planning_direct_overtime(self, attendances):
        if not attendances or "planning.slot" not in self.env:
            return

        overtime_line_model = self.env["hr.attendance.overtime.line"]
        planning_slot_model = self.env["planning.slot"].sudo()
        touched_attendances = self.env["hr.attendance"]

        for attendance in attendances:
            employee = attendance.employee_id
            log_enabled = self._should_log_for_employee(employee)
            if not employee.resource_id:
                if log_enabled:
                    _logger.warning(
                    "[planning_direct_overtime] skip attendance_id=%s reason=no_employee_resource",
                    attendance.id,
                    )
                continue

            version = (
                employee.sudo()._get_version(attendance.check_in.date())
                if hasattr(employee, "_get_version")
                else employee.version_id
            )
            if version and not version.overtime_from_attendance:
                if log_enabled:
                    _logger.warning(
                    "[planning_direct_overtime] skip attendance_id=%s employee_id=%s reason=overtime_from_attendance_false",
                    attendance.id,
                    employee.id,
                    )
                continue

            calendar = (
                (version and version.resource_calendar_id)
                or employee.resource_calendar_id
                or employee.company_id.resource_calendar_id
            )
            if log_enabled:
                _logger.warning(
                    "[planning_direct_overtime] attendance_context attendance_id=%s employee_id=%s "
                    "employee_resource_id=%s version_id=%s work_entry_source=%s overtime_from_attendance=%s "
                    "version_calendar_id=%s employee_calendar_id=%s company_calendar_id=%s chosen_calendar_id=%s chosen_calendar_name=%s",
                    attendance.id,
                    employee.id,
                    employee.resource_id.id if employee.resource_id else False,
                    version.id if version else False,
                    version.work_entry_source if version else False,
                    version.overtime_from_attendance if version else False,
                    version.resource_calendar_id.id if version and version.resource_calendar_id else False,
                    employee.resource_calendar_id.id if employee.resource_calendar_id else False,
                    employee.company_id.resource_calendar_id.id if employee.company_id.resource_calendar_id else False,
                    calendar.id if calendar else False,
                    calendar.name if calendar else False,
                )
            if not calendar:
                if log_enabled:
                    _logger.warning(
                    "[planning_direct_overtime] skip attendance_id=%s employee_id=%s reason=no_calendar",
                    attendance.id,
                    employee.id,
                    )
                continue

            holiday_leaves, holiday_intervals = self._get_public_holiday_intervals(
                attendance, calendar, log_enabled=log_enabled
            )
            holiday_overlap_hours = self._get_overlap_hours(
                attendance.check_in,
                attendance.check_out,
                holiday_intervals,
            )

            slots = planning_slot_model.search(
                [
                    ("resource_id", "=", employee.resource_id.id),
                    ("state", "=", "published"),
                    ("start_datetime", "<", attendance.check_out),
                    ("end_datetime", ">", attendance.check_in),
                ],
                order="start_datetime asc, id asc",
            )
            if not slots and holiday_overlap_hours <= 0.0:
                if log_enabled:
                    _logger.warning(
                    "[planning_direct_overtime] skip attendance_id=%s employee_id=%s reason=no_published_slots_and_no_public_holiday "
                    "source=%s check_in=%s check_out=%s holiday_leave_ids=%s holiday_overlap_hours=%.6f",
                    attendance.id,
                    employee.id,
                    version.work_entry_source if version else False,
                    attendance.check_in,
                    attendance.check_out,
                    holiday_leaves.ids,
                    holiday_overlap_hours,
                    )
                continue

            plan_start = min(slots.mapped("start_datetime")) if slots else False
            plan_end = max(slots.mapped("end_datetime")) if slots else False

            early_extra = 0.0
            if plan_start and attendance.check_in < plan_start:
                early_extra = (plan_start - attendance.check_in).total_seconds() / 3600.0

            late_extra = 0.0
            if plan_end and attendance.check_out > plan_end:
                late_extra = (attendance.check_out - plan_end).total_seconds() / 3600.0

            outside_plan_extra = max(0.0, early_extra + late_extra)
            direct_overtime = round(max(0.0, outside_plan_extra + holiday_overlap_hours), 3)

            overtime_lines = overtime_line_model.search(
                [
                    ("employee_id", "=", employee.id),
                    ("time_start", "=", attendance.check_in),
                    ("time_stop", "=", attendance.check_out),
                ],
                order="id asc",
            )
            if log_enabled:
                _logger.warning(
                    "[planning_direct_overtime] attendance_id=%s employee_id=%s slot_ids=%s holiday_leave_ids=%s "
                    "check_in=%s check_out=%s plan_start=%s plan_end=%s "
                    "early_extra=%.6f late_extra=%.6f holiday_overlap_hours=%.6f "
                    "outside_plan_extra=%.6f direct_overtime=%.6f existing_overtime_line_ids=%s",
                    attendance.id,
                    employee.id,
                    slots.ids,
                    holiday_leaves.ids,
                    attendance.check_in,
                    attendance.check_out,
                    plan_start,
                    plan_end,
                    early_extra,
                    late_extra,
                    holiday_overlap_hours,
                    outside_plan_extra,
                    direct_overtime,
                    overtime_lines.ids,
                )

            if direct_overtime <= 0.0:
                overtime_lines.unlink()
                touched_attendances |= attendance
                if log_enabled:
                    _logger.warning(
                        "[planning_direct_overtime] action=unlink attendance_id=%s removed_overtime_line_ids=%s",
                        attendance.id,
                        overtime_lines.ids,
                    )
                continue

            if overtime_lines:
                primary_line = overtime_lines[:1]
                extra_lines = overtime_lines[1:]
                primary_line.write(
                    {
                        "duration": direct_overtime,
                        "manual_duration": direct_overtime,
                    }
                )
                extra_lines.unlink()
                touched_attendances |= attendance
                if log_enabled:
                    _logger.warning(
                        "[planning_direct_overtime] action=update attendance_id=%s primary_line_id=%s "
                        "new_duration=%.6f removed_extra_line_ids=%s",
                        attendance.id,
                        primary_line.id,
                        direct_overtime,
                        extra_lines.ids,
                    )
                continue

            vals = {
                "employee_id": employee.id,
                "date": attendance.date,
                "time_start": attendance.check_in,
                "time_stop": attendance.check_out,
                "duration": direct_overtime,
                "manual_duration": direct_overtime,
                "amount_rate": 1.0,
            }
            default_rule = (
                version.ruleset_id.rule_ids.sorted("sequence")[:1]
                if version and version.ruleset_id
                else self.env["hr.attendance.overtime.rule"]
            )
            if default_rule:
                vals["rule_ids"] = [(6, 0, default_rule.ids)]
                vals.update(default_rule._extra_overtime_vals())
            created_line = overtime_line_model.create(vals)
            touched_attendances |= attendance
            if log_enabled:
                _logger.warning(
                    "[planning_direct_overtime] action=create attendance_id=%s created_line_id=%s duration=%.6f vals=%s",
                    attendance.id,
                    created_line.id,
                    direct_overtime,
                    vals,
                )

        if touched_attendances:
            self.env.add_to_compute(
                touched_attendances._fields["overtime_hours"],
                touched_attendances,
            )
            self.env.add_to_compute(
                touched_attendances._fields["validated_overtime_hours"],
                touched_attendances,
            )
            self.env.add_to_compute(
                touched_attendances._fields["overtime_status"],
                touched_attendances,
            )
            if hasattr(touched_attendances, "_recompute_recordset"):
                touched_attendances._recompute_recordset(
                    fnames=["overtime_hours", "validated_overtime_hours", "overtime_status"]
                )
            target_recompute_ids = touched_attendances.filtered(
                lambda att: self._should_log_for_employee(att.employee_id)
            ).ids
            if target_recompute_ids:
                _logger.warning(
                    "[planning_direct_overtime] recompute attendance_ids=%s",
                    target_recompute_ids,
                )

