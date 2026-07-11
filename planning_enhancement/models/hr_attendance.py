import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def _ensure_default_ruleset_and_recompute_overtime(self):
        """
        If an employee version misses a ruleset, assign the default attendance
        ruleset and recompute overtime for the impacted attendances.
        """
        default_ruleset = self.env.ref(
            "hr_attendance.hr_attendance_default_ruleset",
            raise_if_not_found=False,
        )
        if not default_ruleset:
            return

        impacted = self.env["hr.attendance"]
        for attendance in self.filtered("employee_id"):
            employee = attendance.employee_id
            version = employee.version_id or employee.current_version_id
            if not version or version.ruleset_id:
                continue
            version.sudo().write({"ruleset_id": default_ruleset.id})
            impacted |= attendance
            _logger.warning(
                (
                    "[planning_enhancement][extra_hours_fix] Assigned default ruleset '%s' "
                    "to employee '%s' version_id=%s while processing attendance_id=%s"
                ),
                default_ruleset.display_name,
                employee.display_name,
                version.id,
                attendance.id,
            )
        if impacted:
            impacted._update_overtime()

    def _debug_log_extra_hours_reason(self, trigger):
        """Emit diagnostic logs to explain why Extra Hours is still 0."""
        for attendance in self:
            employee = attendance.employee_id
            company = employee.company_id
            overtimes = attendance.linked_overtime_ids
            approved_overtimes = overtimes.filtered(lambda ot: ot.status == "approved")
            to_approve_overtimes = overtimes.filtered(lambda ot: ot.status == "to_approve")
            refused_overtimes = overtimes.filtered(lambda ot: ot.status == "refused")

            ruleset = False
            if employee.version_id:
                ruleset = employee.version_id.ruleset_id

            reasons = []
            if not attendance.check_out:
                reasons.append("attendance_is_not_checked_out")
            if not overtimes:
                reasons.append("no_overtime_lines_generated")
                if not ruleset:
                    reasons.append("employee_has_no_ruleset_on_current_version")
            if attendance.validated_overtime_hours == 0:
                if to_approve_overtimes:
                    reasons.append("overtime_pending_manager_approval")
                if refused_overtimes and not approved_overtimes:
                    reasons.append("all_overtime_lines_are_refused")
                if approved_overtimes and not sum(approved_overtimes.mapped("manual_duration")):
                    reasons.append("approved_overtime_duration_is_zero")
                if attendance.overtime_hours == 0:
                    reasons.append("computed_overtime_hours_is_zero")
                if company.attendance_overtime_validation == "by_manager":
                    reasons.append("company_validation_mode_is_by_manager")

            if attendance.validated_overtime_hours or reasons:
                _logger.info(
                    (
                        "[planning_enhancement][extra_hours_debug] trigger=%s attendance_id=%s employee=%s "
                        "date=%s worked_hours=%.2f overtime_hours=%.2f validated_overtime_hours=%.2f "
                        "validation_mode=%s ruleset=%s thresholds(company=%s, employee=%s) "
                        "overtime_lines=%s reasons=%s"
                    ),
                    trigger,
                    attendance.id,
                    employee.display_name,
                    attendance.date,
                    attendance.worked_hours or 0.0,
                    attendance.overtime_hours or 0.0,
                    attendance.validated_overtime_hours or 0.0,
                    company.attendance_overtime_validation,
                    ruleset.display_name if ruleset else "None",
                    company.overtime_company_threshold,
                    company.overtime_employee_threshold,
                    [
                        {
                            "id": ot.id,
                            "status": ot.status,
                            "duration": ot.duration,
                            "manual_duration": ot.manual_duration,
                            "rate": ot.amount_rate,
                        }
                        for ot in overtimes
                    ],
                    ", ".join(reasons) if reasons else "no_blocking_reason_detected",
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_default_ruleset_and_recompute_overtime()
        records._debug_log_extra_hours_reason("create")
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"check_in", "check_out", "employee_id"} & set(vals):
            self._ensure_default_ruleset_and_recompute_overtime()
            self._debug_log_extra_hours_reason("write")
        return res

    def action_approve_overtime(self):
        res = super().action_approve_overtime()
        self._debug_log_extra_hours_reason("action_approve_overtime")
        return res
