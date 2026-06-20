import logging
import traceback

import pytz

from odoo import api, models

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def _aer_get_employee_day_bounds_utc(self, employee, check_in_dt):
        employee_tz = pytz.timezone(employee._get_tz() or "UTC")
        check_in_local = pytz.utc.localize(check_in_dt).astimezone(employee_tz)
        day_start_local = check_in_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end_local = day_start_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        return (
            day_start_local.astimezone(pytz.utc).replace(tzinfo=None),
            day_end_local.astimezone(pytz.utc).replace(tzinfo=None),
            employee_tz,
        )

    def _aer_get_expected_hours(self, attendance):
        employee = attendance.employee_id
        if not employee or not attendance.check_in:
            return 0.0, "no_employee_or_check_in", {}

        version = employee.sudo()._get_version(attendance.check_in.date()) if hasattr(employee, "_get_version") else employee.version_id
        work_entry_source = (version.work_entry_source or "") if version else ""
        overtime_from_attendance = bool(version.overtime_from_attendance) if version else False
        day_start_utc, day_end_utc, employee_tz = self._aer_get_employee_day_bounds_utc(employee, attendance.check_in)

        details = {
            "work_entry_source": work_entry_source or "n/a",
            "overtime_from_attendance": overtime_from_attendance,
            "day_start_utc": day_start_utc,
            "day_end_utc": day_end_utc,
            "employee_tz": employee_tz.zone,
        }

        if (
            work_entry_source == "planning"
            and overtime_from_attendance
            and employee.resource_id
            and "planning.slot" in self.env
        ):
            slots = self.env["planning.slot"].sudo().search([
                ("resource_id", "=", employee.resource_id.id),
                ("state", "=", "published"),
                ("start_datetime", "<", day_end_utc),
                ("end_datetime", ">", day_start_utc),
            ])
            expected_hours = sum(slots.mapped("duration"))
            details["slot_ids"] = slots.ids
            return expected_hours, "planning_published_slots", details

        schedule_intervals = employee._employee_attendance_intervals(
            pytz.utc.localize(day_start_utc),
            pytz.utc.localize(day_end_utc),
        )
        expected_hours = sum((end - start).total_seconds() for start, end, _meta in schedule_intervals) / 3600.0
        return expected_hours, "resource_calendar", details

    def _aer_log_extra_hours_reason(self, attendances, trigger):
        overtime_line_model = self.env["hr.attendance.overtime.line"]
        for attendance in attendances:
            employee = attendance.employee_id
            if not employee:
                continue
            employee_tz_name = employee._get_tz() or employee.tz or "UTC"
            employee_tz = pytz.timezone(employee_tz_name)
            check_in_local = (
                pytz.utc.localize(attendance.check_in).astimezone(employee_tz)
                if attendance.check_in
                else False
            )
            check_out_local = (
                pytz.utc.localize(attendance.check_out).astimezone(employee_tz)
                if attendance.check_out
                else False
            )

            overtime_lines = overtime_line_model.search([
                ("employee_id", "=", employee.id),
                ("time_start", "=", attendance.check_in),
            ])
            expected_hours, expected_source, expected_details = self._aer_get_expected_hours(attendance)
            worked_hours = attendance.worked_hours or 0.0
            overtime_hours = sum(overtime_lines.mapped("manual_duration"))
            approved_overtime_hours = sum(
                overtime_lines.filtered(lambda line: line.status == "approved").mapped("manual_duration")
            )
            reasons = []
            if not attendance.check_out:
                reasons.append("attendance_not_closed")
            if not overtime_lines:
                reasons.append("no_overtime_lines_generated")
            if overtime_lines and not approved_overtime_hours:
                reasons.append("lines_exist_but_not_approved")
            if overtime_hours > 0:
                reasons.append("worked_hours_exceeded_expected_or_timing_rules_applied")
            if worked_hours <= expected_hours:
                reasons.append("timing_or_non_workday_rules_may_have_generated_overtime")

            _logger.warning(
                (
                    "[attendance_extra_hours_reason_log] trigger=%s attendance_id=%s employee_id=%s employee=%s "
                    "check_in_utc=%s check_out_utc=%s check_in_local=%s check_out_local=%s "
                    "employee_tz=%s worked_hours=%.4f expected_hours=%.4f expected_source=%s "
                    "delta_worked_minus_expected=%.4f overtime_hours=%.4f validated_overtime_hours=%.4f "
                    "attendance_overtime_hours_field=%.4f attendance_validated_field=%.4f "
                    "attendance_authorization_request=%s overtime_lines=%s expected_details=%s reasons=%s"
                ),
                trigger,
                attendance.id,
                employee.id,
                employee.display_name,
                attendance.check_in,
                attendance.check_out,
                check_in_local,
                check_out_local,
                employee_tz_name,
                worked_hours,
                expected_hours,
                expected_source,
                worked_hours - expected_hours,
                overtime_hours,
                approved_overtime_hours,
                attendance.overtime_hours or 0.0,
                attendance.validated_overtime_hours or 0.0,
                (
                    {
                        "id": attendance.overtime_authorization_request_id.id,
                        "status": attendance.overtime_authorization_request_id.request_status,
                        "quantity": attendance.overtime_authorization_request_id.quantity,
                        "preauthorization": attendance.overtime_authorization_request_id.overtime_preauthorization,
                        "consumed": attendance.overtime_authorization_request_id.overtime_authorization_consumed,
                    }
                    if hasattr(attendance, "overtime_authorization_request_id")
                    and attendance.overtime_authorization_request_id
                    else False
                ),
                [
                    {
                        "id": line.id,
                        "date": line.date,
                        "status": line.status,
                        "duration": line.duration,
                        "manual_duration": line.manual_duration,
                        "amount_rate": line.amount_rate,
                        "time_start_utc": line.time_start,
                        "time_stop_utc": line.time_stop,
                        "time_start_local": (
                            pytz.utc.localize(line.time_start).astimezone(employee_tz)
                            if line.time_start
                            else False
                        ),
                        "time_stop_local": (
                            pytz.utc.localize(line.time_stop).astimezone(employee_tz)
                            if line.time_stop
                            else False
                        ),
                        "line_tz": employee_tz_name,
                        "approval_request_ids": line.approval_request_ids.ids,
                        "approval_requests": [
                            {
                                "id": req.id,
                                "status": req.request_status,
                                "quantity": req.quantity,
                                "preauthorization": req.overtime_preauthorization,
                                "consumed": req.overtime_authorization_consumed,
                            }
                            for req in line.approval_request_ids
                        ],
                        "rules": [
                            {
                                "id": rule.id,
                                "name": rule.name,
                                "base_off": rule.base_off,
                                "timing_type": rule.timing_type,
                                "quantity_period": rule.quantity_period,
                                "expected_hours_from_contract": rule.expected_hours_from_contract,
                                "expected_hours": rule.expected_hours,
                                "employer_tolerance": rule.employer_tolerance,
                                "employee_tolerance": rule.employee_tolerance,
                            }
                            for rule in line.rule_ids
                        ],
                    }
                    for line in overtime_lines
                ],
                expected_details,
                ", ".join(reasons) if reasons else "no_reason_detected",
            )

    def _update_overtime(self, attendance_domain=None):
        result = super()._update_overtime(attendance_domain=attendance_domain)
        impacted_attendances = (self | self.env["hr.attendance"].search(attendance_domain or [])).filtered(
            lambda att: att.check_in and att.employee_id
        )
        if impacted_attendances:
            if hasattr(impacted_attendances, "_recompute_recordset"):
                impacted_attendances._recompute_recordset(
                    fnames=["overtime_hours", "validated_overtime_hours", "overtime_status"]
                )
            self._aer_log_extra_hours_reason(impacted_attendances, trigger="_update_overtime")
        return result

    def action_log_extra_hours_reason(self):
        self._aer_log_extra_hours_reason(self, trigger="manual_action_log_extra_hours_reason")
        return True


class HrAttendanceOvertimeLine(models.Model):
    _inherit = "hr.attendance.overtime.line"

    @api.model
    def _aer_infer_source_from_stack(self):
        stack = traceback.extract_stack()
        frames = []
        for frame in stack:
            path = frame.filename.replace("\\", "/")
            if "/odoo/" not in path:
                continue
            if "/attendance_extra_hours_reason_log/" in path:
                continue
            if "/python" in path and "/site-packages/" in path:
                continue
            frames.append(
                {
                    "path": path,
                    "func": frame.name,
                    "line": frame.lineno,
                }
            )

        source = "unknown"
        for frame in reversed(frames):
            path = frame["path"]
            if "/custom_module/hr_attendance_overtime_approval_bridge/" in path:
                source = "custom_module_hr_attendance_overtime_approval_bridge"
                break
            if "/hr_attendance_overtime_approval_bridge/" in path:
                source = "hr_attendance_overtime_approval_bridge"
                break
            if "/addons/hr_attendance/models/hr_attendance.py" in path:
                source = "core_hr_attendance_update_overtime"
                break

        return source, frames[-12:]

    def _aer_log_line_source(self, action, records, vals_list=None):
        source, stack_tail = self._aer_infer_source_from_stack()
        vals_payload = vals_list if vals_list is not None else []
        for line in records:
            _logger.warning(
                (
                    "[attendance_extra_hours_reason_log][line_source] action=%s source=%s "
                    "line_id=%s employee_id=%s date=%s status=%s duration=%s manual_duration=%s "
                    "time_start=%s time_stop=%s approval_request_ids=%s vals_payload=%s stack_tail=%s"
                ),
                action,
                source,
                line.id,
                line.employee_id.id,
                line.date,
                line.status,
                line.duration,
                line.manual_duration,
                line.time_start,
                line.time_stop,
                line.approval_request_ids.ids if "approval_request_ids" in line._fields else [],
                vals_payload,
                stack_tail,
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._aer_log_line_source("create", records, vals_list=vals_list)
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"duration", "manual_duration", "status", "time_start", "time_stop"} & set(vals):
            self._aer_log_line_source("write", self, vals_list=[vals])
        return res
