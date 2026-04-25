# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


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
            attendance.overtime_authorization_request_id._sync_authorized_attendance_overtime()
