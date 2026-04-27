# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrAttendanceOvertimeLine(models.Model):
    _inherit = "hr.attendance.overtime.line"

    approval_request_ids = fields.Many2many(
        "approval.request",
        "approval_request_hr_overtime_rel",
        "overtime_line_id",
        "request_id",
        string="Approval Requests",
        copy=False,
    )

    def _get_approved_request(self):
        self.ensure_one()
        return self.approval_request_ids.filtered(
            lambda req: req.request_status == "approved"
        )[:1]

    def _check_overtime_approval_gate(self):
        lines_to_check = self.filtered(
            lambda line: line.employee_id.company_id.attendance_overtime_validation == "by_manager"
        )
        if not lines_to_check:
            return

        blocked_lines = lines_to_check.filtered(lambda line: not line._get_approved_request())
        if blocked_lines:
            raise UserError(
                _(
                    "Cannot approve extra hours before the related Approval Request "
                    "is approved in the Approvals app."
                )
            )

    def _queue_linked_attendance_recompute(self):
        attendances = self._linked_attendances()
        if not attendances:
            return
        field_names = [
            "overtime_hours",
            "validated_overtime_hours",
            "overtime_status",
        ]
        for field_name in field_names:
            self.env.add_to_compute(
                attendances._fields[field_name],
                attendances,
            )
        attendances._recompute_recordset(
            fnames=field_names,
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._queue_linked_attendance_recompute()
        return records

    def action_approve(self):
        if not self.env.context.get("skip_overtime_approval_gate"):
            self._check_overtime_approval_gate()
        return super().action_approve()

    def write(self, vals):
        if any(key in vals for key in ["status", "manual_duration", "time_start"]):
            self._queue_linked_attendance_recompute()
        return super().write(vals)

