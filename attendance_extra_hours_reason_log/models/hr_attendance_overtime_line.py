import logging
import traceback

from odoo import api, models

_logger = logging.getLogger(__name__)


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
            if "/hr_attendance_overtime_approval_bridge/" in path:
                source = "hr_attendance_overtime_approval_bridge"
                break
            if "/addons/hr_attendance/models/hr_attendance.py" in path:
                source = "core_hr_attendance_update_overtime"
                break
            if "/custom_module/hr_attendance_overtime_approval_bridge/" in path:
                source = "custom_module_hr_attendance_overtime_approval_bridge"
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
