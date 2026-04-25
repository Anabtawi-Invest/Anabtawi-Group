# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)

CONFIG_PARAM_KEY = "hr_attendance_weekly_overtime_eligibility.required_weekly_hours"


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
    overtime_preauthorization = fields.Boolean(
        string="Overtime Preauthorization",
        copy=False,
        readonly=True,
        help="Technical flag indicating that this request authorizes a future overtime session before attendance overtime lines exist.",
    )
    overtime_authorized_attendance_id = fields.Many2one(
        "hr.attendance",
        string="Authorized Attendance",
        copy=False,
        readonly=True,
    )
    overtime_authorization_consumed = fields.Boolean(
        string="Authorization Consumed",
        copy=False,
        readonly=True,
    )
    overtime_authorization_state = fields.Selection(
        [
            ("waiting_approval", "Waiting Approval"),
            ("available", "Available"),
            ("reserved", "Reserved"),
            ("consumed", "Consumed"),
        ],
        string="Authorization Status",
        compute="_compute_overtime_authorization_state",
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
            domain = [
                ("employee_id", "=", request.overtime_employee_id.id),
                ("date", ">=", request.overtime_date_from),
                ("date", "<=", request.overtime_date_to),
                ("status", "in", ["to_approve", "refused", "approved"]),
            ]
            request.overtime_line_ids = overtime_line_model.search(domain)
            all_lines = overtime_line_model.search(
                [
                    ("employee_id", "=", request.overtime_employee_id.id),
                    ("date", ">=", request.overtime_date_from),
                    ("date", "<=", request.overtime_date_to),
                ]
            )
            _logger.warning(
                "Overtime request %s line lookup employee=%s period=%s..%s domain=%s matched_ids=%s matched_statuses=%s matched_hours=%s all_ids=%s all_statuses=%s all_hours=%s",
                request.id or "new",
                request.overtime_employee_id.id,
                request.overtime_date_from,
                request.overtime_date_to,
                domain,
                request.overtime_line_ids.ids,
                request.overtime_line_ids.mapped("status"),
                request.overtime_line_ids.mapped("manual_duration"),
                all_lines.ids,
                all_lines.mapped("status"),
                all_lines.mapped("manual_duration"),
            )

    @api.depends("overtime_line_ids", "quantity", "is_overtime_category")
    def _compute_overtime_data(self):
        for request in self:
            request.is_overtime_request = bool(
                request.is_overtime_category or request.overtime_line_ids
            )
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

    @api.depends(
        "is_overtime_category",
        "overtime_preauthorization",
        "request_status",
        "overtime_authorized_attendance_id",
        "overtime_authorization_consumed",
    )
    def _compute_overtime_authorization_state(self):
        for request in self:
            if not request.is_overtime_category or not request.overtime_preauthorization:
                request.overtime_authorization_state = False
            elif request.overtime_authorization_consumed:
                request.overtime_authorization_state = "consumed"
            elif request.overtime_authorized_attendance_id:
                request.overtime_authorization_state = "reserved"
            elif request.request_status == "approved":
                request.overtime_authorization_state = "available"
            else:
                request.overtime_authorization_state = "waiting_approval"

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

    @api.model
    def _get_required_weekly_hours(self):
        value = self.env["ir.config_parameter"].sudo().get_param(
            CONFIG_PARAM_KEY, default="0.0"
        )
        return float(value or 0.0)

    def _check_requested_overtime_hours_limit(self):
        for request in self.filtered("is_overtime_category"):
            if request.quantity <= 0:
                raise ValidationError(_("Requested Overtime Hours must be greater than zero."))
            if not request.overtime_line_ids:
                continue
            available_hours = sum(request.overtime_line_ids.mapped("manual_duration"))
            _logger.warning(
                "Overtime request %s requested_hours=%s available_hours=%s overtime_line_ids=%s statuses=%s durations=%s employee=%s period=%s..%s",
                request.id or "new",
                request.quantity,
                available_hours,
                request.overtime_line_ids.ids,
                request.overtime_line_ids.mapped("status"),
                request.overtime_line_ids.mapped("manual_duration"),
                request.overtime_employee_id.id,
                request.overtime_date_from,
                request.overtime_date_to,
            )
            if request.quantity > available_hours:
                raise ValidationError(
                    _(
                        "Requested Overtime Hours cannot exceed available overtime in the selected period. "
                        "Available: %(available)s",
                        available=available_hours,
                    )
                )

    def _check_weekly_worked_hours_eligibility(self):
        required_weekly_hours = self._get_required_weekly_hours()
        if required_weekly_hours <= 0:
            return

        for request in self.filtered("is_overtime_category"):
            employee = request.overtime_employee_id
            if not employee:
                continue
            if "weekly_worked_hours" not in employee._fields:
                raise ValidationError(
                    _(
                        "Weekly worked hours eligibility is not available. "
                        "Please install the weekly overtime eligibility module first."
                    )
                )
            weekly_worked_hours = employee.weekly_worked_hours
            if float_compare(
                weekly_worked_hours, required_weekly_hours, precision_digits=2
            ) < 0:
                raise ValidationError(
                    _(
                        "Employee %(employee)s cannot submit the overtime approval request "
                        "because Weekly Worked Hours (%(worked)s) did not reach the "
                        "required weekly hours (%(required)s).",
                        employee=employee.display_name,
                        worked=weekly_worked_hours,
                        required=required_weekly_hours,
                    )
                )

    @api.model
    def _get_available_preauthorized_request(self, employee, target_date=None):
        target_date = target_date or fields.Date.context_today(employee)
        domain = [
            ("is_overtime_category", "=", True),
            ("overtime_employee_id", "=", employee.id),
            ("overtime_preauthorization", "=", True),
            ("request_status", "=", "approved"),
            ("overtime_authorization_consumed", "=", False),
            ("overtime_authorized_attendance_id", "=", False),
            ("overtime_date_from", "<=", target_date),
            ("overtime_date_to", ">=", target_date),
        ]
        return self.search(domain, order="overtime_date_from asc, create_date asc, id asc", limit=1)

    def _reserve_preauthorized_attendance(self, attendance):
        self.ensure_one()
        if not self.overtime_preauthorization:
            raise ValidationError(_("This overtime request cannot be used as a preauthorized overtime session."))
        if self.request_status != "approved":
            raise ValidationError(_("Only approved overtime requests can unlock overtime check-in."))
        if self.overtime_authorization_consumed or self.overtime_authorized_attendance_id:
            raise ValidationError(_("This overtime authorization has already been used."))
        self.write({"overtime_authorized_attendance_id": attendance.id})

    def _sync_authorized_attendance_overtime(self):
        for request in self.filtered(
            lambda req: req.overtime_preauthorization
            and req.request_status == "approved"
            and req.overtime_authorized_attendance_id
            and not req.overtime_authorization_consumed
        ):
            attendance = request.overtime_authorized_attendance_id
            if not attendance.check_out:
                continue

            overtime_lines = attendance.linked_overtime_ids
            if overtime_lines:
                overtime_lines.write(
                    {"approval_request_ids": [Command.link(request.id)]}
                )
                overtime_lines.with_context(skip_overtime_approval_gate=True).action_approve()
            request.write({"overtime_authorization_consumed": True})

    @api.constrains("is_overtime_category", "quantity", "overtime_line_ids")
    def _check_requested_hours(self):
        self._check_requested_overtime_hours_limit()

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
        for request in self.filtered(lambda req: req.is_overtime_category and req.overtime_employee_id):
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
        overtime_requests = self.filtered("is_overtime_category")
        preauthorized_requests = overtime_requests.filtered(lambda req: not req.overtime_line_ids)
        preauthorized_requests.write({"overtime_preauthorization": True})
        (overtime_requests - preauthorized_requests).write({"overtime_preauthorization": False})
        (overtime_requests - preauthorized_requests)._check_requested_overtime_hours_limit()
        overtime_requests._check_weekly_worked_hours_eligibility()
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
                                "status": "refused",
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
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)

CONFIG_PARAM_KEY = "hr_attendance_weekly_overtime_eligibility.required_weekly_hours"


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
    overtime_preauthorization = fields.Boolean(
        string="Overtime Preauthorization",
        copy=False,
        readonly=True,
        help="Technical flag indicating that this request authorizes a future overtime session before attendance overtime lines exist.",
    )
    overtime_authorized_attendance_id = fields.Many2one(
        "hr.attendance",
        string="Authorized Attendance",
        copy=False,
        readonly=True,
    )
    overtime_authorization_consumed = fields.Boolean(
        string="Authorization Consumed",
        copy=False,
        readonly=True,
    )
    overtime_authorization_state = fields.Selection(
        [
            ("waiting_approval", "Waiting Approval"),
            ("available", "Available"),
            ("reserved", "Reserved"),
            ("consumed", "Consumed"),
        ],
        string="Authorization Status",
        compute="_compute_overtime_authorization_state",
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
            domain = [
                ("employee_id", "=", request.overtime_employee_id.id),
                ("date", ">=", request.overtime_date_from),
                ("date", "<=", request.overtime_date_to),
                # Portal and backend users may request approval after attendance overtime
                # has already been marked approved in Attendances.
                ("status", "in", ["to_approve", "refused", "approved"]),
            ]
            request.overtime_line_ids = overtime_line_model.search(domain)
            all_lines = overtime_line_model.search(
                [
                    ("employee_id", "=", request.overtime_employee_id.id),
                    ("date", ">=", request.overtime_date_from),
                    ("date", "<=", request.overtime_date_to),
                ]
            )
            _logger.warning(
                "Overtime request %s line lookup employee=%s period=%s..%s domain=%s matched_ids=%s matched_statuses=%s matched_hours=%s all_ids=%s all_statuses=%s all_hours=%s",
                request.id or "new",
                request.overtime_employee_id.id,
                request.overtime_date_from,
                request.overtime_date_to,
                domain,
                request.overtime_line_ids.ids,
                request.overtime_line_ids.mapped("status"),
                request.overtime_line_ids.mapped("manual_duration"),
                all_lines.ids,
                all_lines.mapped("status"),
                all_lines.mapped("manual_duration"),
            )

    @api.depends("overtime_line_ids", "quantity", "is_overtime_category")
    def _compute_overtime_data(self):
        for request in self:
            request.is_overtime_request = bool(
                request.is_overtime_category or request.overtime_line_ids
            )
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

    @api.depends(
        "is_overtime_category",
        "overtime_preauthorization",
        "request_status",
        "overtime_authorized_attendance_id",
        "overtime_authorization_consumed",
    )
    def _compute_overtime_authorization_state(self):
        for request in self:
            if not request.is_overtime_category or not request.overtime_preauthorization:
                request.overtime_authorization_state = False
            elif request.overtime_authorization_consumed:
                request.overtime_authorization_state = "consumed"
            elif request.overtime_authorized_attendance_id:
                request.overtime_authorization_state = "reserved"
            elif request.request_status == "approved":
                request.overtime_authorization_state = "available"
            else:
                request.overtime_authorization_state = "waiting_approval"

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

    @api.model
    def _get_required_weekly_hours(self):
        value = self.env["ir.config_parameter"].sudo().get_param(
            CONFIG_PARAM_KEY, default="0.0"
        )
        return float(value or 0.0)

    def _check_requested_overtime_hours_limit(self):
        for request in self.filtered("is_overtime_category"):
            if request.quantity <= 0:
                raise ValidationError(_("Requested Overtime Hours must be greater than zero."))
            if not request.overtime_line_ids:
                continue
            available_hours = sum(request.overtime_line_ids.mapped("manual_duration"))
            _logger.warning(
                "Overtime request %s requested_hours=%s available_hours=%s overtime_line_ids=%s statuses=%s durations=%s employee=%s period=%s..%s",
                request.id or "new",
                request.quantity,
                available_hours,
                request.overtime_line_ids.ids,
                request.overtime_line_ids.mapped("status"),
                request.overtime_line_ids.mapped("manual_duration"),
                request.overtime_employee_id.id,
                request.overtime_date_from,
                request.overtime_date_to,
            )
            if request.quantity > available_hours:
                raise ValidationError(
                    _(
                        "Requested Overtime Hours cannot exceed available overtime in the selected period. "
                        "Available: %(available)s",
                        available=available_hours,
                    )
                )

    def _check_weekly_worked_hours_eligibility(self):
        required_weekly_hours = self._get_required_weekly_hours()
        if required_weekly_hours <= 0:
            return

        for request in self.filtered("is_overtime_category"):
            employee = request.overtime_employee_id
            if not employee:
                continue
            if "weekly_worked_hours" not in employee._fields:
                raise ValidationError(
                    _(
                        "Weekly worked hours eligibility is not available. "
                        "Please install the weekly overtime eligibility module first."
                    )
                )
            weekly_worked_hours = employee.weekly_worked_hours
            if float_compare(
                weekly_worked_hours, required_weekly_hours, precision_digits=2
            ) < 0:
                raise ValidationError(
                    _(
                        "Employee %(employee)s cannot submit the overtime approval request "
                        "because Weekly Worked Hours (%(worked)s) did not reach the "
                        "required weekly hours (%(required)s).",
                        employee=employee.display_name,
                        worked=weekly_worked_hours,
                        required=required_weekly_hours,
                    )
                )

    @api.model
    def _get_available_preauthorized_request(self, employee, target_date=None):
        target_date = target_date or fields.Date.context_today(employee)
        domain = [
            ("is_overtime_category", "=", True),
            ("overtime_employee_id", "=", employee.id),
            ("overtime_preauthorization", "=", True),
            ("request_status", "=", "approved"),
            ("overtime_authorization_consumed", "=", False),
            ("overtime_authorized_attendance_id", "=", False),
            ("overtime_date_from", "<=", target_date),
            ("overtime_date_to", ">=", target_date),
        ]
        return self.search(domain, order="overtime_date_from asc, create_date asc, id asc", limit=1)

    def _reserve_preauthorized_attendance(self, attendance):
        self.ensure_one()
        if not self.overtime_preauthorization:
            raise ValidationError(_("This overtime request cannot be used as a preauthorized overtime session."))
        if self.request_status != "approved":
            raise ValidationError(_("Only approved overtime requests can unlock overtime check-in."))
        if self.overtime_authorization_consumed or self.overtime_authorized_attendance_id:
            raise ValidationError(_("This overtime authorization has already been used."))
        self.write({"overtime_authorized_attendance_id": attendance.id})

    def _sync_authorized_attendance_overtime(self):
        for request in self.filtered(
            lambda req: req.overtime_preauthorization
            and req.request_status == "approved"
            and req.overtime_authorized_attendance_id
            and not req.overtime_authorization_consumed
        ):
            attendance = request.overtime_authorized_attendance_id
            if not attendance.check_out:
                continue

            overtime_lines = attendance.linked_overtime_ids
            if overtime_lines:
                overtime_lines.write(
                    {"approval_request_ids": [Command.link(request.id)]}
                )
                overtime_lines.with_context(skip_overtime_approval_gate=True).action_approve()
            request.write({"overtime_authorization_consumed": True})

    @api.constrains("is_overtime_category", "quantity", "overtime_line_ids")
    def _check_requested_hours(self):
        self._check_requested_overtime_hours_limit()

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
        for request in self.filtered(lambda req: req.is_overtime_category and req.overtime_employee_id):
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
        overtime_requests = self.filtered("is_overtime_category")
        preauthorized_requests = overtime_requests.filtered(lambda req: not req.overtime_line_ids)
        preauthorized_requests.write({"overtime_preauthorization": True})
        (overtime_requests - preauthorized_requests).write({"overtime_preauthorization": False})
        (overtime_requests - preauthorized_requests)._check_requested_overtime_hours_limit()
        overtime_requests._check_weekly_worked_hours_eligibility()
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
                                # The approval request becomes the final decision source.
                                # Any remaining hours beyond the approved quantity should
                                # not stay pending in Attendances.
                                "status": "refused",
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

