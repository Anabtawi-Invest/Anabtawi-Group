from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class HrAttendanceExtraHoursApproval(models.Model):
    _name = "hr.attendance.extra.hours.approval"
    _description = "Extra Hours Approval"
    _order = "date desc, id desc"
    _rec_name = "employee_id"

    _attendance_unique = models.Constraint(
        "unique(attendance_id)",
        "An extra hours approval already exists for this attendance.",
    )

    attendance_id = fields.Many2one(
        "hr.attendance",
        string="Attendance",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        related="attendance_id.employee_id",
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="employee_id.company_id",
        store=True,
        index=True,
    )
    manager_id = fields.Many2one(
        "hr.employee",
        string="Manager",
        related="employee_id.parent_id",
        store=True,
        index=True,
    )
    date = fields.Date(required=True, index=True)
    extra_hours = fields.Float(string="Extra Hours")
    state = fields.Selection(
        selection=[
            ("waiting", "Waiting manager approval"),
            ("approved", "Approved"),
            ("refused", "Refused by manager"),
        ],
        default="waiting",
        required=True,
        index=True,
    )
    decided_by_id = fields.Many2one("res.users", string="Decided By", readonly=True)
    decided_on = fields.Datetime(string="Decided On", readonly=True)

    @api.model
    def _ensure_for_attendances(self, attendances):
        """Create one waiting approval for every attendance that has extra hours."""
        attendances = attendances.filtered(
            lambda att: att.id and att.employee_id and att.check_in and att.check_out
        )
        if not attendances:
            return self.browse()

        lines = self.env["hr.attendance.overtime.line"].sudo().search(
            [
                ("employee_id", "in", attendances.employee_id.ids),
                ("time_start", "in", list(set(attendances.mapped("check_in")))),
            ]
        )
        existing = self.sudo().search([("attendance_id", "in", attendances.ids)])
        by_attendance = {approval.attendance_id.id: approval for approval in existing}
        created = self.browse()
        for attendance in attendances:
            matched = lines.filtered(
                lambda line, attendance=attendance: line.employee_id == attendance.employee_id
                and line.time_start == attendance.check_in
            )
            hours = sum(matched.mapped("manual_duration"))
            if float_compare(hours, 0.0, precision_digits=2) <= 0:
                hours = sum(matched.mapped("duration"))
            if float_compare(hours, 0.0, precision_digits=2) <= 0:
                continue
            current = by_attendance.get(attendance.id)
            if current:
                if (
                    current.state == "waiting"
                    and float_compare(current.extra_hours, hours, precision_digits=2) != 0
                ):
                    current.sudo().write({"extra_hours": hours})
            else:
                current = self.sudo().create(
                    {
                        "attendance_id": attendance.id,
                        "date": fields.Date.to_date(attendance.check_in),
                        "extra_hours": hours,
                    }
                )
                created |= current
            if current.state == "waiting":
                self._hold_lines_for_manager(matched)
        return existing | created

    @api.model
    def _hold_lines_for_manager(self, lines):
        """Keep extra hours editable in Attendance after the manager unlocks them.

        Lines that were approved automatically, and not by an approval request,
        go back to To Approve so both attendance buttons can appear later.
        """
        pending_lines = lines.filtered(
            lambda line: line.status == "approved"
            and not line.approval_request_ids.filtered(
                lambda request: request.request_status == "approved"
            )
        )
        if pending_lines:
            pending_lines.sudo().with_context(skip_overtime_approval_gate=True).write(
                {"status": "to_approve"}
            )

    def _decide(self, new_state, user=None):
        if any(approval.state != "waiting" for approval in self):
            raise UserError(_("This extra hours request was already decided."))
        user = user or self.env.user
        self.sudo().write(
            {
                "state": new_state,
                "decided_by_id": user.id,
                "decided_on": fields.Datetime.now(),
            }
        )
        return True

    def _check_backend_decider(self):
        user = self.env.user
        is_officer = user.has_group("hr_attendance.group_hr_attendance_officer")
        for approval in self:
            manager_user = approval.manager_id.user_id
            if is_officer or (manager_user and manager_user == user):
                continue
            raise UserError(
                _("Only the employee's manager can decide this extra hours request.")
            )

    def action_manager_approve(self):
        self._check_backend_decider()
        return self._decide("approved")

    def action_manager_refuse(self):
        self._check_backend_decider()
        return self._decide("refused")
