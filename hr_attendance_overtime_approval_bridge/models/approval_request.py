# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    overtime_line_ids = fields.Many2many(
        "hr.attendance.overtime.line",
        "approval_request_hr_overtime_rel",
        "request_id",
        "overtime_line_id",
        string="Overtime Lines",
        compute="_compute_overtime_line_ids",
        store=True,
        readonly=True,
        copy=False,
    )
    is_overtime_category = fields.Boolean(
        related="category_id.is_overtime_category",
        string="Is Overtime Category",
        readonly=True,
    )
    overtime_employee_id = fields.Many2one(
        "hr.employee",
        string="Overtime Employee",
        copy=False,
    )
    overtime_date_from = fields.Date(
        string="Overtime Date From",
        copy=False,
    )
    overtime_date_to = fields.Date(
        string="Overtime Date To",
        copy=False,
    )
    overtime_total_hours = fields.Float(
        string="Total Overtime Hours",
        compute="_compute_overtime_data",
        store=True,
        readonly=True,
    )
    is_overtime_request = fields.Boolean(
        string="Is Overtime Request",
        compute="_compute_overtime_data",
        store=True,
    )

    @api.onchange("request_owner_id", "category_id")
    def _onchange_overtime_defaults(self):
        for request in self:
            if not request.is_overtime_category:
                continue
            if request.request_status != "new":
                continue
            if not request.overtime_employee_id and request.request_owner_id:
                request.overtime_employee_id = self.env["hr.employee"].search(
                    [("user_id", "=", request.request_owner_id.id)],
                    limit=1,
                )
            if not request.overtime_date_from:
                request.overtime_date_from = (
                    (request.date_start and fields.Datetime.to_date(request.date_start))
                    or (request.date and fields.Datetime.to_date(request.date))
                )
            if not request.overtime_date_to:
                request.overtime_date_to = (
                    (request.date_end and fields.Datetime.to_date(request.date_end))
                    or (request.date and fields.Datetime.to_date(request.date))
                )

    @api.depends("overtime_employee_id", "overtime_date_from", "overtime_date_to", "is_overtime_category")
    def _compute_overtime_line_ids(self):
        overtime_line_model = self.env["hr.attendance.overtime.line"]
        for request in self:
            if (
                not request.is_overtime_category
                or not request.overtime_employee_id
                or not request.overtime_date_from
                or not request.overtime_date_to
            ):
                request.overtime_line_ids = False
                continue
            request.overtime_line_ids = overtime_line_model.search(
                [
                    ("employee_id", "=", request.overtime_employee_id.id),
                    ("date", ">=", request.overtime_date_from),
                    ("date", "<=", request.overtime_date_to),
                    ("status", "in", ["to_approve", "refused"]),
                ]
            )

    @api.depends("overtime_line_ids", "quantity", "is_overtime_category")
    def _compute_overtime_data(self):
        for request in self:
            request.is_overtime_request = bool(request.overtime_line_ids)
            if not request.is_overtime_category:
                request.overtime_total_hours = sum(request.overtime_line_ids.mapped("manual_duration"))
                continue
            requested_hours = request.quantity
            if requested_hours <= 0:
                request.overtime_total_hours = 0.0
                continue
            remaining = requested_hours
            total = 0.0
            for overtime_line in request.overtime_line_ids.sorted(lambda l: (l.date, l.time_start or fields.Datetime.now())):
                if remaining <= 0:
                    break
                approved_chunk = min(overtime_line.manual_duration, remaining)
                total += approved_chunk
                remaining -= approved_chunk
            request.overtime_total_hours = total

    @api.constrains("overtime_line_ids")
    def _check_overtime_lines_same_employee(self):
        for request in self.filtered("overtime_line_ids"):
            if len(request.overtime_line_ids.employee_id) > 1:
                raise ValidationError(_("All overtime lines in one request must belong to the same employee."))

    @api.constrains("overtime_line_ids", "request_owner_id")
    def _check_overtime_request_owner(self):
        for request in self.filtered("overtime_line_ids"):
            employee = request.overtime_employee_id
            if not employee or not employee.user_id:
                raise ValidationError(
                    _("The selected overtime lines must belong to an employee linked to a user.")
                )
            if request.request_owner_id != employee.user_id:
                raise ValidationError(
                    _("The Request Owner must be the same user as the overtime employee.")
                )

    @api.constrains("is_overtime_category", "overtime_employee_id", "overtime_date_from", "overtime_date_to")
    def _check_overtime_fields(self):
        for request in self.filtered("is_overtime_category"):
            if not request.overtime_employee_id:
                raise ValidationError(_("Overtime Employee is required for overtime approval requests."))
            if not request.overtime_date_from or not request.overtime_date_to:
                raise ValidationError(_("Overtime Date From and Overtime Date To are required."))
            if request.overtime_date_to < request.overtime_date_from:
                raise ValidationError(_("Overtime Date To must be on or after Overtime Date From."))

    @api.constrains("is_overtime_category", "quantity", "overtime_line_ids")
    def _check_requested_hours(self):
        for request in self.filtered("is_overtime_category"):
            if request.quantity <= 0:
                raise ValidationError(_("Requested Overtime Hours must be greater than zero."))
            available_hours = sum(request.overtime_line_ids.mapped("manual_duration"))
            if request.quantity > available_hours:
                raise ValidationError(
                    _(
                        "Requested Overtime Hours cannot exceed available overtime in the selected period. "
                        "Available: %(available)s",
                        available=available_hours,
                    )
                )

    @api.constrains("overtime_line_ids", "request_status")
    def _check_single_open_overtime_request(self):
        open_statuses = ("new", "pending")
        for request in self.filtered(lambda req: req.overtime_line_ids and req.request_status in open_statuses):
            conflict_domain = [
                ("id", "!=", request.id),
                ("request_status", "in", open_statuses),
                ("overtime_line_ids", "in", request.overtime_line_ids.ids),
            ]
            if self.search_count(conflict_domain):
                raise ValidationError(
                    _("Each overtime line can only have one open approval request at a time.")
                )

    def _ensure_overtime_manager_approver(self):
        for request in self.filtered("overtime_line_ids"):
            manager_user = request.overtime_employee_id.attendance_manager_id
            if not manager_user:
                raise UserError(
                    _("The overtime employee must have an Attendance Manager before submitting this request.")
                )

            manager_approver = request.approver_ids.filtered(lambda approver: approver.user_id == manager_user)
            if manager_approver:
                manager_approver.write({"required": True})
                continue

            request.write(
                {
                    "approver_ids": [
                        Command.create(
                            {
                                "user_id": manager_user.id,
                                "required": True,
                                "sequence": 1,
                            }
                        )
                    ]
                }
            )

    def action_confirm(self):
        self._ensure_overtime_manager_approver()
        return super().action_confirm()

    def _sync_overtime_lines_with_status(self):
        overtime_requests = self.filtered("overtime_line_ids")
        for request in overtime_requests:
            if request.request_status == "approved":
                remaining = request.quantity
                for overtime_line in request.overtime_line_ids.sorted(
                    lambda line: (line.date, line.time_start or fields.Datetime.now())
                ):
                    if remaining <= 0:
                        continue
                    approved_chunk = min(overtime_line.manual_duration, remaining)
                    original_duration = overtime_line.manual_duration
                    if approved_chunk < original_duration:
                        overtime_line.copy(
                            {
                                "duration": original_duration - approved_chunk,
                                "manual_duration": original_duration - approved_chunk,
                                "status": "to_approve",
                            }
                        )
                    overtime_line.write({"duration": approved_chunk, "manual_duration": approved_chunk})
                    overtime_line.with_context(skip_overtime_approval_gate=True).action_approve()
                    remaining -= approved_chunk
            elif request.request_status == "refused":
                request.overtime_line_ids.action_refuse()

    def action_approve(self, approver=None):
        result = super().action_approve(approver=approver)
        self._sync_overtime_lines_with_status()
        return result

    def action_refuse(self, approver=None):
        result = super().action_refuse(approver=approver)
        self._sync_overtime_lines_with_status()
        return result

    def _action_force_approval(self):
        result = super()._action_force_approval()
        self._sync_overtime_lines_with_status()
        return result

