import logging

from odoo import api, models


_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    @api.depends("check_in", "check_out", "employee_id")
    def _compute_overtime_hours(self):
        super()._compute_overtime_hours()
        for attendance in self:
            line_details = [
                {
                    "line_id": line.id,
                    "status": line.status,
                    "duration": line.duration,
                    "manual_duration": line.manual_duration,
                    "credited_duration": getattr(line, "credited_duration", line.manual_duration),
                    "work_entry_type": line.work_entry_type_id.code
                    or line.work_entry_type_id.display_name
                    or "N/A",
                    "rules": line.rule_ids.mapped("name"),
                }
                for line in attendance.linked_overtime_ids
            ]
            _logger.info(
                "[extra_hours_enhancement] Worked Extra Hours computed: "
                "attendance_id=%s employee=%s check_in=%s check_out=%s "
                "linked_lines=%s total_worked_extra_hours=%s",
                attendance.id,
                attendance.employee_id.display_name,
                attendance.check_in,
                attendance.check_out,
                line_details,
                attendance.overtime_hours,
            )

    @api.depends("check_in", "check_out", "employee_id")
    def _compute_validated_overtime_hours(self):
        super()._compute_validated_overtime_hours()
        for attendance in self:
            approved_lines = attendance.linked_overtime_ids.filtered_domain(
                [("status", "=", "approved")]
            )
            line_details = [
                {
                    "line_id": line.id,
                    "status": line.status,
                    "duration": line.duration,
                    "manual_duration": line.manual_duration,
                    "credited_duration": getattr(line, "credited_duration", line.manual_duration),
                    "work_entry_type": line.work_entry_type_id.code
                    or line.work_entry_type_id.display_name
                    or "N/A",
                    "rules": line.rule_ids.mapped("name"),
                }
                for line in approved_lines
            ]
            _logger.info(
                "[extra_hours_enhancement] Approved Extra Hours computed: "
                "attendance_id=%s employee=%s approved_lines=%s "
                "total_approved_extra_hours=%s",
                attendance.id,
                attendance.employee_id.display_name,
                line_details,
                attendance.validated_overtime_hours,
            )
