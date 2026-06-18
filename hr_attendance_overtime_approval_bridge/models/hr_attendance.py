# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    overtime_authorization_request_id = fields.Many2one(
        "approval.request",
        string="Overtime Authorization Request",
        copy=False,
        readonly=True,
    )
    overtime_authorization_deadline = fields.Datetime(
        string="Overtime Authorization Deadline",
        copy=False,
        readonly=True,
    )

    @api.depends("check_in", "check_out", "employee_id")
    def _compute_overtime_status(self):
        for attendance in self:
            linked_overtimes = attendance.linked_overtime_ids
            if not linked_overtimes:
                attendance.overtime_status = False
            elif any(linked_overtimes.mapped(lambda ot: ot.status == "to_approve")):
                attendance.overtime_status = "to_approve"
            elif any(linked_overtimes.mapped(lambda ot: ot.status == "approved")):
                attendance.overtime_status = "approved"
            else:
                attendance.overtime_status = "refused"

    def _finalize_overtime_authorization(self):
        for attendance in self.filtered(
            lambda att: att.overtime_authorization_request_id and att.check_out
        ):
            _logger.warning(
                "Overtime authorization finalize: attendance_id=%s employee_id=%s request_id=%s "
                "check_in=%s check_out=%s worked_hours=%s linked_overtime_ids=%s validated_overtime_hours=%s",
                attendance.id,
                attendance.employee_id.id,
                attendance.overtime_authorization_request_id.id,
                attendance.check_in,
                attendance.check_out,
                attendance.worked_hours,
                attendance.linked_overtime_ids.ids,
                attendance.validated_overtime_hours,
            )
            attendance.overtime_authorization_request_id._sync_authorized_attendance_overtime()

    def _update_overtime(self, attendance_domain=None):
        """Guard against core min()/max() crash on empty attendance dates."""
        try:
            return super()._update_overtime(attendance_domain=attendance_domain)
        except ValueError as err:
            if "min() iterable argument is empty" not in str(err):
                raise
            _logger.warning(
                "Skipped overtime recomputation due to empty attendance dates: "
                "attendance_ids=%s domain=%s error=%s",
                self.ids,
                attendance_domain,
                err,
            )
            return

    def _cron_auto_check_out_overtime_authorizations(self):
        deadline_now = fields.Datetime.now()
        attendances = self.search(
            [
                ("overtime_authorization_request_id", "!=", False),
                ("overtime_authorization_request_id.overtime_disable_auto_checkout", "=", False),
                ("overtime_authorization_deadline", "!=", False),
                ("check_out", "=", False),
                ("overtime_authorization_deadline", "<=", deadline_now),
            ]
        )
        _logger.warning(
            "Overtime authorization auto check-out cron: now=%s attendance_ids=%s",
            deadline_now,
            attendances.ids,
        )
        for attendance in attendances:
            deadline = attendance.overtime_authorization_deadline
            if deadline and attendance.check_in and deadline <= attendance.check_in:
                deadline = attendance.check_in + timedelta(seconds=1)
            _logger.warning(
                "Overtime authorization auto check-out: attendance_id=%s employee_id=%s request_id=%s "
                "check_in=%s deadline=%s final_check_out=%s",
                attendance.id,
                attendance.employee_id.id,
                attendance.overtime_authorization_request_id.id,
                attendance.check_in,
                attendance.overtime_authorization_deadline,
                deadline,
            )
            attendance.write(
                {
                    "check_out": deadline,
                    "out_mode": "auto_check_out",
                }
            )

    def write(self, vals):
        authorized_before = self.filtered("overtime_authorization_request_id")
        result = super().write(vals)
        if any(field in vals for field in ("employee_id", "check_in", "check_out")):
            authorized_after = self.filtered(
                lambda att: att.overtime_authorization_request_id and att.check_out
            )
            for attendance in authorized_before:
                _logger.warning(
                    "Overtime authorization attendance write: attendance_id=%s request_id=%s vals=%s "
                    "check_in=%s check_out=%s worked_hours=%s out_mode=%s",
                    attendance.id,
                    attendance.overtime_authorization_request_id.id,
                    vals,
                    attendance.check_in,
                    attendance.check_out,
                    attendance.worked_hours,
                    attendance.out_mode,
                )
            authorized_after._finalize_overtime_authorization()
        return result
