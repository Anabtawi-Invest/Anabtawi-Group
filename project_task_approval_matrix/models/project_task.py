from markupsafe import Markup, escape

from odoo import Command, api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


EDITABLE_APPROVAL_STATES = ("draft", "changes_requested", "rejected")
ACTIVE_APPROVAL_STATES = ("submitted", "partially_approved")
APPROVAL_DECISION_FIELDS = {
    "approval_state",
    "submitted_by_id",
    "submitted_date",
    "approved_date",
}
APPROVAL_CONFIGURATION_FIELDS = {
    "approval_required",
    "approval_type",
    "approval_line_ids",
}
ALLOCATION_FIELDS = {
    "allocation_value",
    "allocation_unit",
    "allocation_calendar_id",
}


class ProjectTask(models.Model):
    _inherit = "project.task"

    project_approval_enabled = fields.Boolean(
        related="project_id.approval_matrix_enabled",
        string="Project Approval Enabled",
        store=True,
        readonly=True,
    )
    approval_required = fields.Boolean(
        string="Requires Approval",
        default=False,
        tracking=True,
        copy=True,
    )
    approval_type = fields.Selection(
        selection=[
            ("sequential", "Sequential"),
            ("parallel", "Parallel"),
        ],
        string="Approval Type",
        default="sequential",
        required=True,
        tracking=True,
        copy=True,
    )
    approval_state = fields.Selection(
        selection=[
            ("not_required", "Not Required"),
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("partially_approved", "Partially Approved"),
            ("approved", "Approved"),
            ("changes_requested", "Changes Requested"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        string="Approval Status",
        default="not_required",
        tracking=True,
        copy=False,
        index=True,
        readonly=True,
    )
    submitted_by_id = fields.Many2one(
        "res.users",
        string="Submitted By",
        readonly=True,
        copy=False,
    )
    submitted_date = fields.Datetime(
        string="Submitted Date",
        readonly=True,
        copy=False,
    )
    approved_date = fields.Datetime(
        string="Final Approval Date",
        readonly=True,
        copy=False,
    )
    approval_progress = fields.Float(
        string="Approval Progress",
        compute="_compute_approval_progress",
        store=True,
    )
    approval_count = fields.Integer(
        string="Approval Steps",
        compute="_compute_approval_count",
    )
    pending_approval_count = fields.Integer(
        string="Pending Approvals",
        compute="_compute_approval_count",
    )
    current_approver_ids = fields.Many2many(
        "res.users",
        "project_task_current_approver_rel",
        "task_id",
        "user_id",
        string="Current Approvers",
        compute="_compute_current_approvers",
        store=True,
    )
    current_approver_id = fields.Many2one(
        "res.users",
        string="Primary Current Approver",
        compute="_compute_current_approvers",
        store=True,
    )
    approval_line_ids = fields.One2many(
        "project.task.approval.line",
        "task_id",
        string="Approvers",
        copy=True,
    )
    can_current_user_approve = fields.Boolean(
        compute="_compute_approval_action_flags",
    )
    can_submit_approval = fields.Boolean(
        compute="_compute_approval_action_flags",
    )
    can_reset_approval = fields.Boolean(
        compute="_compute_approval_action_flags",
    )
    can_manager_override = fields.Boolean(
        compute="_compute_approval_action_flags",
    )
    approval_manager_override_reason = fields.Text(
        string="Manager Override Reason",
        copy=False,
        help="Required when an Approval Manager uses the controlled override action.",
    )
    allocation_unit = fields.Selection(
        selection=[
            ("hours", "Hours"),
            ("days", "Days"),
        ],
        string="Allocation Unit",
        default="hours",
        required=True,
        tracking=True,
        copy=True,
    )
    allocation_value = fields.Float(
        string="Allocation Value",
        tracking=True,
        copy=True,
    )
    allocation_calendar_id = fields.Many2one(
        "resource.calendar",
        string="Allocation Calendar",
        copy=True,
        check_company=True,
        help=(
            "Calendar used to convert allocated days into hours. If empty, use "
            "the main assigned employee or company calendar."
        ),
    )

    @api.depends("approval_line_ids.state")
    def _compute_approval_progress(self):
        for task in self:
            total = len(task.approval_line_ids)
            approved = len(
                task.approval_line_ids.filtered(lambda line: line.state == "approved")
            )
            task.approval_progress = (approved * 100.0 / total) if total else 0.0

    @api.depends("approval_line_ids.state")
    def _compute_approval_count(self):
        for task in self:
            task.approval_count = len(task.approval_line_ids)
            task.pending_approval_count = len(
                task.approval_line_ids.filtered(lambda line: line.state == "pending")
            )

    @api.depends("approval_line_ids.state", "approval_line_ids.approver_id")
    def _compute_current_approvers(self):
        for task in self:
            current_approvers = task.approval_line_ids.filtered(
                lambda line: line.state == "pending"
            ).approver_id
            task.current_approver_ids = current_approvers
            task.current_approver_id = current_approvers[:1]

    @api.depends(
        "project_approval_enabled",
        "approval_required",
        "approval_state",
        "approval_line_ids.state",
        "approval_line_ids.approver_id",
    )
    @api.depends_context("uid")
    def _compute_approval_action_flags(self):
        is_approver = self.env.user.has_group(
            "project_task_approval_matrix.group_project_task_approver"
        )
        is_manager = self.env.user.has_group(
            "project_task_approval_matrix.group_project_approval_manager"
        )
        for task in self:
            task.can_current_user_approve = (
                is_approver
                and task.project_approval_enabled
                and task.approval_required
                and bool(
                    task.approval_line_ids.filtered(
                        lambda line: line.state == "pending"
                        and line.approver_id == self.env.user
                    )
                )
            )
            task.can_submit_approval = (
                task.project_approval_enabled
                and task.approval_required
                and task.approval_state in EDITABLE_APPROVAL_STATES
            )
            task.can_reset_approval = (
                is_manager
                and task.project_approval_enabled
                and task.approval_required
                and task.approval_state != "draft"
            )
            task.can_manager_override = (
                is_manager
                and task.project_approval_enabled
                and task.approval_required
                and task.approval_state != "approved"
            )

    def _is_approval_manager(self):
        return self.env.user.has_group(
            "project_task_approval_matrix.group_project_approval_manager"
        )

    def _approval_workflow_write(self, values):
        """Apply trusted workflow values after the public action checks."""
        return super().write(values)

    def _approval_lines_sudo(self):
        """Return the complete route after task access has been checked."""
        self.ensure_one()
        return self.sudo().approval_line_ids.sorted(lambda line: (line.sequence, line.id))

    def _post_approval_audit(self, message):
        """Post an internal, actor-attributed approval audit note."""
        for task in self:
            project_name = task.project_id.display_name or _("No Project")
            timestamp = fields.Datetime.to_string(fields.Datetime.now())
            audit_text = _(
                "%(message)s | Task: %(task)s | Project: %(project)s | "
                "Actor: %(actor)s | Date: %(date)s",
                message=message,
                task=task.display_name,
                project=project_name,
                actor=self.env.user.display_name,
                date=timestamp,
            )
            task.message_post(
                body=Markup("<p>%s</p>") % escape(audit_text),
                subtype_xmlid="mail.mt_note",
            )

    def _notify_assignees(self, message):
        for task in self:
            partner_ids = task.user_ids.partner_id.ids
            if partner_ids:
                task.message_post(
                    body=Markup("<p>%s</p>") % escape(message),
                    partner_ids=partner_ids,
                    message_type="notification",
                    subtype_xmlid="mail.mt_note",
                )

    def _send_approval_email(self, template_xmlid, recipients):
        self.ensure_one()
        if not self.project_id.send_approval_email_notifications:
            return
        emails = recipients.mapped("partner_id.email")
        emails = [email for email in emails if email]
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template and emails:
            template.sudo().send_mail(
                self.id,
                force_send=False,
                email_values={"email_to": ",".join(emails)},
            )

    def _create_line_activity(self, line):
        self.ensure_one()
        self.message_subscribe(partner_ids=line.approver_id.partner_id.ids)
        note = _(
            "Task: %(task)s\nProject: %(project)s\nApproval sequence: %(sequence)s\n"
            "Submitted by: %(submitter)s",
            task=self.display_name,
            project=self.project_id.display_name,
            sequence=line.sequence,
            submitter=self.submitted_by_id.display_name,
        )
        self.activity_schedule(
            "project_task_approval_matrix.mail_activity_type_task_approval",
            summary=_("Task approval required"),
            note=Markup("<p>%s</p>") % escape(note).replace("\n", Markup("<br/>")),
            user_id=line.approver_id.id,
            project_task_approval_line_id=line.id,
        )
        self._post_approval_audit(
            _(
                "Approval step %(sequence)s activated for %(approver)s.",
                sequence=line.sequence,
                approver=line.approver_id.display_name,
            )
        )
        self._send_approval_email(
            "project_task_approval_matrix.mail_template_task_approval_pending",
            line.approver_id,
        )

    def _close_line_activities(self, lines, feedback):
        activities = self.env["mail.activity"].sudo().search(
            [
                ("project_task_approval_line_id", "in", lines.ids),
                ("res_model", "=", "project.task"),
                ("res_id", "=", self.id),
            ]
        )
        if activities:
            # Technical sudo is limited to the exact activities linked to the
            # authorized approval route. It is needed when closing another
            # approver's stale activity.
            activities.action_feedback(feedback=feedback)

    def _validate_approval_route(self, allow_self_approval=False):
        self.ensure_one()
        self.check_access("read")
        if not self.project_approval_enabled:
            raise UserError(_("The task's project does not use the approval matrix."))
        if not self.approval_required:
            raise UserError(_("This task does not require approval."))
        if self.state == "1_canceled" or self.approval_state == "cancelled":
            raise UserError(_("A cancelled task cannot be submitted for approval."))
        if self.approval_state == "approved":
            raise UserError(_("This task is already fully approved."))
        if self.approval_state in ACTIVE_APPROVAL_STATES:
            raise UserError(_("An approval round is already active."))

        lines = self._approval_lines_sudo()
        if not lines:
            raise ValidationError(_("Add at least one approver before submission."))
        if len(lines.approver_id) != len(lines):
            raise ValidationError(
                _("The same approver cannot be added twice to the same task.")
            )
        invalid_users = lines.filtered(
            lambda line: not line.approver_id.active or line.approver_id.share
        )
        if invalid_users:
            raise ValidationError(_("All approvers must be active internal users."))
        if self.company_id and lines.filtered(
            lambda line: self.company_id not in line.approver_id.company_ids
        ):
            raise ValidationError(
                _("Every approver must have access to the task company.")
            )
        if self.approval_type == "sequential":
            if any(line.sequence <= 0 for line in lines):
                raise ValidationError(
                    _("Sequential approval steps require a positive sequence.")
                )
            if len(set(lines.mapped("sequence"))) != len(lines):
                raise ValidationError(
                    _("Sequential approval steps must use unique sequence values.")
                )
        if lines.filtered(lambda line: line.state == "pending"):
            raise UserError(
                _("Resolve or reset the pending approval round before resubmission.")
            )
        if (
            self.project_id.prevent_self_approval
            and not allow_self_approval
            and self.user_ids & lines.approver_id
        ):
            raise ValidationError(
                _("Task assignees cannot be approvers when self-approval is prevented.")
            )
        return lines

    def _start_approval_round(self, allow_self_approval=False):
        self.ensure_one()
        lines = self._validate_approval_route(
            allow_self_approval=allow_self_approval
        )
        now = fields.Datetime.now()
        self._close_line_activities(lines, _("Previous approval round closed"))
        lines._workflow_write(
            {
                "state": "waiting",
                "submitted_date": now,
                "decision_date": False,
                "decided_by_id": False,
                "comments": False,
            }
        )
        self.sudo()._approval_workflow_write(
            {
                "approval_state": "submitted",
                "submitted_by_id": self.env.user.id,
                "submitted_date": now,
                "approved_date": False,
            }
        )
        if self.approval_type == "sequential":
            active_lines = lines[:1]
        else:
            active_lines = lines
        active_lines._workflow_write({"state": "pending"})
        self._post_approval_audit(_("Task submitted for approval."))
        for line in active_lines:
            self._create_line_activity(line)
        return lines

    def action_submit_for_approval(self):
        if not self.env.user.has_group("project.group_project_user"):
            raise AccessError(_("Only internal Project users may submit approvals."))
        for task in self:
            task._start_approval_round()
        return True

    def _pending_line_for_current_user(self):
        self.ensure_one()
        self.check_access("read")
        if not self.env.user.has_group(
            "project_task_approval_matrix.group_project_task_approver"
        ):
            raise AccessError(_("You are not a Project Task Approver."))
        line = self._approval_lines_sudo().filtered(
            lambda route_line: route_line.state == "pending"
            and route_line.approver_id == self.env.user
        )
        if len(line) != 1:
            raise AccessError(
                _("Only the assigned pending approver may take this action.")
            )
        return line

    def _finalize_approval(self):
        self.ensure_one()
        lines = self._approval_lines_sudo()
        now = fields.Datetime.now()
        self.sudo()._approval_workflow_write(
            {
                "approval_state": "approved",
                "approved_date": now,
            }
        )
        self._close_line_activities(lines, _("Task approval completed"))
        self._post_approval_audit(_("Final approval completed."))
        self._notify_assignees(
            _("All required approvals for task %s are complete.", self.display_name)
        )
        self._send_approval_email(
            "project_task_approval_matrix.mail_template_task_approval_complete",
            self.user_ids,
        )

    def action_approve(self):
        for task in self:
            line = task._pending_line_for_current_user()
            now = fields.Datetime.now()
            line._workflow_write(
                {
                    "state": "approved",
                    "decision_date": now,
                    "decided_by_id": self.env.user.id,
                }
            )
            task._close_line_activities(line, _("Approval step approved"))
            task._post_approval_audit(
                _(
                    "Approval step %(sequence)s approved. Comments: %(comments)s",
                    sequence=line.sequence,
                    comments=line.comments or _("None"),
                )
            )
            lines = task._approval_lines_sudo()
            if all(route_line.state == "approved" for route_line in lines):
                task._finalize_approval()
            elif task.approval_type == "sequential":
                next_line = lines.filtered(lambda route_line: route_line.state == "waiting")[:1]
                next_line._workflow_write({"state": "pending"})
                task._create_line_activity(next_line)
            else:
                task.sudo()._approval_workflow_write(
                    {"approval_state": "partially_approved"}
                )
        return True

    def _action_negative_decision(self, decision):
        if decision not in ("changes_requested", "rejected"):
            raise ValueError("Unsupported approval decision")
        for task in self:
            line = task._pending_line_for_current_user()
            if not (line.comments or "").strip():
                label = (
                    _("change request")
                    if decision == "changes_requested"
                    else _("rejection")
                )
                raise ValidationError(_("Comments are required for this %s.", label))
            now = fields.Datetime.now()
            lines = task._approval_lines_sudo()
            line._workflow_write(
                {
                    "state": decision,
                    "decision_date": now,
                    "decided_by_id": self.env.user.id,
                }
            )
            (lines - line).filtered(
                lambda route_line: route_line.state in ("pending", "waiting")
            )._workflow_write({"state": "cancelled"})
            task._close_line_activities(lines, _("Approval round closed"))
            task.sudo()._approval_workflow_write(
                {
                    "approval_state": decision,
                    "approved_date": False,
                }
            )
            decision_label = (
                _("Changes requested")
                if decision == "changes_requested"
                else _("Approval rejected")
            )
            task._post_approval_audit(
                _(
                    "%(decision)s at step %(sequence)s. Comments: %(comments)s",
                    decision=decision_label,
                    sequence=line.sequence,
                    comments=line.comments,
                )
            )
            task._notify_assignees(
                _(
                    "%(decision)s for task %(task)s: %(comments)s",
                    decision=decision_label,
                    task=task.display_name,
                    comments=line.comments,
                )
            )
            task._send_approval_email(
                "project_task_approval_matrix.mail_template_task_approval_decision",
                task.user_ids,
            )
        return True

    def action_request_changes(self):
        return self._action_negative_decision("changes_requested")

    def action_reject(self):
        return self._action_negative_decision("rejected")

    def action_reset_approval(self):
        if not self._is_approval_manager():
            raise AccessError(_("Only Approval Managers may reset approvals."))
        for task in self:
            task.check_access("read")
            lines = task._approval_lines_sudo()
            task._close_line_activities(lines, _("Approval workflow reset"))
            lines._workflow_write(
                {
                    "state": "waiting",
                    "submitted_date": False,
                    "decision_date": False,
                    "decided_by_id": False,
                    "comments": False,
                }
            )
            task.sudo()._approval_workflow_write(
                {
                    "approval_state": "draft" if task.approval_required else "not_required",
                    "submitted_by_id": False,
                    "submitted_date": False,
                    "approved_date": False,
                    "approval_manager_override_reason": False,
                }
            )
            task._post_approval_audit(_("Approval workflow reset."))
        return True

    def action_manager_override_approve(self):
        if not self._is_approval_manager():
            raise AccessError(_("Only Approval Managers may use the approval override."))
        for task in self:
            if task.state == "1_canceled" or task.approval_state == "cancelled":
                raise UserError(_("A cancelled task cannot be approved by override."))
            reason = (task.approval_manager_override_reason or "").strip()
            if not reason:
                raise ValidationError(_("A manager override reason is required."))
            if task.approval_state in EDITABLE_APPROVAL_STATES:
                lines = task._start_approval_round(allow_self_approval=True)
            else:
                task.check_access("read")
                lines = task._approval_lines_sudo()
                if not lines:
                    raise ValidationError(_("The task has no approval route."))
            now = fields.Datetime.now()
            lines.filtered(
                lambda line: line.state in ("waiting", "pending")
            )._workflow_write(
                {
                    "state": "approved",
                    "decision_date": now,
                    "decided_by_id": self.env.user.id,
                    "comments": reason,
                }
            )
            task._post_approval_audit(
                _("Approval Manager override used. Comments: %s", reason)
            )
            task.sudo()._approval_workflow_write(
                {"approval_manager_override_reason": False}
            )
            task._finalize_approval()
        return True

    def _resolve_allocation_calendar(self, values=None):
        """Resolve task, employee, company, then fallback calendars."""
        self.ensure_one()
        values = values or {}
        calendar_id = values.get("allocation_calendar_id")
        if calendar_id is not None:
            calendar = self.env["resource.calendar"].browse(calendar_id)
        else:
            calendar = self.allocation_calendar_id
        if calendar:
            return calendar

        if "user_ids" in values:
            user_ids = list(
                self._fields["user_ids"].convert_to_cache(values["user_ids"], self)
            )
            users = self.env["res.users"].browse(user_ids)
        else:
            users = self.user_ids

        project_id = values.get("project_id")
        project = (
            self.env["project.project"].browse(project_id)
            if project_id is not None
            else self.project_id
        )
        company = project.company_id or self.company_id or self.env.company
        if users:
            main_user = users[:1]
            employee = self.env["hr.employee"].sudo().search(
                [
                    ("user_id", "in", main_user.ids),
                    ("company_id", "=", company.id),
                ],
                order="id",
                limit=1,
            )
            if employee.resource_calendar_id:
                return employee.resource_calendar_id
        return company.resource_calendar_id

    def _prepare_allocated_hours(self, values=None):
        """Convert the task's allocation value to standard allocated hours."""
        self.ensure_one()
        values = values or {}
        unit = values.get("allocation_unit", self.allocation_unit or "hours")
        value = values.get("allocation_value", self.allocation_value or 0.0)
        if value < 0:
            raise ValidationError(_("Allocated time cannot be negative."))
        if unit == "hours":
            return value
        calendar = self._resolve_allocation_calendar(values)
        hours_per_day = calendar.hours_per_day if calendar else 8.0
        return value * (hours_per_day or 8.0)

    @api.onchange(
        "allocation_value",
        "allocation_unit",
        "allocation_calendar_id",
        "user_ids",
        "project_id",
    )
    def _onchange_allocation_values(self):
        for task in self:
            task.allocated_hours = task._prepare_allocated_hours()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group(
            "project_task_approval_matrix.group_project_approval_manager"
        ) and any(
            values.get("approval_required")
            or values.get("approval_line_ids")
            for values in vals_list
        ):
            raise AccessError(
                _("Only Approval Managers may configure task approval routes.")
            )
        prepared_vals_list = []
        for original_values in vals_list:
            values = dict(original_values)
            project = self.env["project.project"].browse(values.get("project_id"))
            if not project and values.get("parent_id"):
                project = self.browse(values["parent_id"]).project_id
            approval_required = bool(values.get("approval_required", False))
            if approval_required and not project.approval_matrix_enabled:
                raise ValidationError(
                    _("Approval cannot be enabled when the project matrix is disabled.")
                )
            supplied_state = values.pop("approval_state", None)
            expected_state = "draft" if approval_required else "not_required"
            if supplied_state and supplied_state != expected_state:
                raise AccessError(
                    _("Approval decision status cannot be assigned during task creation.")
                )
            values["approval_state"] = expected_state
            for field_name in (
                "submitted_by_id",
                "submitted_date",
                "approved_date",
            ):
                if values.get(field_name):
                    raise AccessError(
                        _("Approval decision fields cannot be imported directly.")
                    )
                values.pop(field_name, None)

            closing_stage = self.env["project.task.type"].browse(
                values.get("stage_id")
            )
            if (
                approval_required
                and project.prevent_task_completion_without_approval
                and (
                    closing_stage.approval_closing_stage
                    or values.get("state") == "1_done"
                )
            ):
                raise UserError(
                    _(
                        "This task cannot be completed until all required "
                        "approvals are approved."
                    )
                )

            if ALLOCATION_FIELDS & set(values):
                if "allocation_value" not in values:
                    values["allocation_value"] = values.get("allocated_hours", 0.0)
                temporary = self.new(values)
                values["allocated_hours"] = temporary._prepare_allocated_hours(values)
            elif "allocated_hours" in values:
                values["allocation_unit"] = "hours"
                values["allocation_value"] = values["allocated_hours"]
            prepared_vals_list.append(values)
        tasks = super().create(prepared_vals_list)
        for task in tasks.filtered("approval_required"):
            task._post_approval_audit(_("Approval enabled on task."))
        return tasks

    def _check_completion_before_write(self, values):
        target_stage = (
            self.env["project.task.type"].browse(values["stage_id"])
            if values.get("stage_id")
            else self.env["project.task.type"]
        )
        target_done = values.get("state") == "1_done"
        for task in self:
            project = (
                self.env["project.project"].browse(values["project_id"])
                if values.get("project_id")
                else task.project_id
            )
            required = values.get("approval_required", task.approval_required)
            if not (
                project.approval_matrix_enabled
                and required
                and project.prevent_task_completion_without_approval
                and task.approval_state != "approved"
            ):
                continue
            if target_done or target_stage.approval_closing_stage:
                raise UserError(
                    _(
                        "This task cannot be completed until all required "
                        "approvals are approved."
                    )
                )

    def write(self, values):
        values = dict(values)
        if "approval_manager_override_reason" in values and not self._is_approval_manager():
            raise AccessError(
                _("Only Approval Managers may enter an override reason.")
            )
        if set(values) & APPROVAL_DECISION_FIELDS:
            raise AccessError(
                _("Approval decision fields can only be changed by workflow actions.")
            )

        configuration_change = bool(
            set(values) & APPROVAL_CONFIGURATION_FIELDS
        )
        if configuration_change:
            if not self._is_approval_manager():
                raise AccessError(
                    _("Only Approval Managers may configure task approval routes.")
                )
            if self.filtered(
                lambda task: task.approval_state not in EDITABLE_APPROVAL_STATES
                and task.approval_state != "not_required"
            ):
                raise UserError(
                    _("Reset the approval workflow before changing its configuration.")
                )

        if "approval_required" in values:
            values["approval_state"] = (
                "draft" if values["approval_required"] else "not_required"
            )

        if "project_id" in values or values.get("approval_required"):
            target_project = (
                self.env["project.project"].browse(values["project_id"])
                if values.get("project_id")
                else self.project_id
            )
            for task in self:
                project = target_project if len(target_project) == 1 else task.project_id
                required = values.get("approval_required", task.approval_required)
                if required and not project.approval_matrix_enabled:
                    raise ValidationError(
                        _(
                            "Approval cannot be enabled when the project matrix "
                            "is disabled."
                        )
                    )

        self._check_completion_before_write(values)

        allocation_change = bool(ALLOCATION_FIELDS & set(values))
        direct_hours_change = "allocated_hours" in values and not allocation_change
        allocation_source_change = bool(
            {"user_ids", "project_id"} & set(values)
        ) and not direct_hours_change
        result = True
        if allocation_change or direct_hours_change or allocation_source_change:
            for task in self:
                task_values = dict(values)
                if allocation_change or allocation_source_change:
                    task_values["allocated_hours"] = task._prepare_allocated_hours(
                        task_values
                    )
                else:
                    task_values["allocation_unit"] = "hours"
                    task_values["allocation_value"] = task_values["allocated_hours"]
                result = super(ProjectTask, task).write(task_values) and result
        else:
            result = super().write(values)

        if "approval_required" in values:
            for task in self:
                lines = task._approval_lines_sudo()
                if not task.approval_required:
                    task._close_line_activities(
                        lines, _("Approval no longer required")
                    )
                    lines.filtered(
                        lambda line: line.state in ("waiting", "pending")
                    )._workflow_write({"state": "cancelled"})
                else:
                    task._post_approval_audit(_("Approval enabled on task."))
        elif configuration_change:
            for task in self:
                task._post_approval_audit(
                    _("Approval configuration changed before submission.")
                )

        if values.get("state") == "1_canceled":
            for task in self.filtered(
                lambda record: record.project_approval_enabled
                and record.approval_required
                and record.approval_state != "approved"
            ):
                lines = task._approval_lines_sudo()
                task._close_line_activities(lines, _("Task cancelled"))
                lines.filtered(
                    lambda line: line.state in ("waiting", "pending")
                )._workflow_write({"state": "cancelled"})
                task.sudo()._approval_workflow_write(
                    {"approval_state": "cancelled"}
                )
                task._post_approval_audit(_("Approval cancelled with task."))
        return result

    def copy_data(self, default=None):
        defaults = dict(default or {})
        values_list = super().copy_data(default=defaults)
        for task, values in zip(self, values_list):
            approval_required = defaults.get(
                "approval_required", task.approval_required
            )
            values.update(
                {
                    "approval_state": "draft" if approval_required else "not_required",
                    "submitted_by_id": False,
                    "submitted_date": False,
                    "approved_date": False,
                    "approval_manager_override_reason": False,
                }
            )
        return values_list
