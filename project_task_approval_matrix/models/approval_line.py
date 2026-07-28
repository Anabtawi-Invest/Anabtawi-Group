from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


EDITABLE_TASK_STATES = ("draft", "changes_requested", "rejected")
CONFIGURATION_FIELDS = {"sequence", "approver_id", "approver_role"}
DECISION_FIELDS = {
    "state",
    "submitted_date",
    "decision_date",
    "decided_by_id",
}


class ProjectTaskApprovalLine(models.Model):
    _name = "project.task.approval.line"
    _description = "Project Task Approval Line"
    _order = "sequence, id"
    _inherit = ["mail.thread"]

    task_id = fields.Many2one(
        "project.task",
        string="Task",
        required=True,
        ondelete="cascade",
        index=True,
        copy=False,
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
        required=True,
        copy=True,
    )
    approver_id = fields.Many2one(
        "res.users",
        string="Approver",
        required=True,
        domain=[("share", "=", False), ("active", "=", True)],
        index=True,
        copy=True,
    )
    approver_role = fields.Char(
        string="Approval Role",
        copy=True,
    )
    state = fields.Selection(
        selection=[
            ("waiting", "Waiting"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("changes_requested", "Changes Requested"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="waiting",
        required=True,
        tracking=True,
        index=True,
        copy=False,
    )
    submitted_date = fields.Datetime(
        string="Submitted Date",
        readonly=True,
        copy=False,
    )
    decision_date = fields.Datetime(
        string="Decision Date",
        readonly=True,
        copy=False,
    )
    decided_by_id = fields.Many2one(
        "res.users",
        string="Decision By",
        readonly=True,
        copy=False,
    )
    comments = fields.Text(
        string="Comments",
        copy=False,
    )
    is_current_user = fields.Boolean(
        compute="_compute_current_user_flags",
    )
    can_take_action = fields.Boolean(
        compute="_compute_current_user_flags",
    )
    company_id = fields.Many2one(
        "res.company",
        related="task_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )

    _unique_task_approver = models.Constraint(
        "UNIQUE(task_id, approver_id)",
        "The same approver cannot be added twice to the same task.",
    )
    _positive_sequence = models.Constraint(
        "CHECK(sequence > 0)",
        "Approval sequence must be greater than zero.",
    )

    @api.depends("approver_id", "state")
    @api.depends_context("uid")
    def _compute_current_user_flags(self):
        for line in self:
            line.is_current_user = line.approver_id == self.env.user
            line.can_take_action = (
                line.state == "pending"
                and line.approver_id == self.env.user
                and self.env.user.has_group(
                    "project_task_approval_matrix.group_project_task_approver"
                )
            )

    @api.constrains("approver_id", "task_id")
    def _check_approver_company_and_type(self):
        for line in self:
            if line.approver_id.share or not line.approver_id.active:
                raise ValidationError(_("Approvers must be active internal users."))
            task_company = line.task_id.company_id
            if task_company and task_company not in line.approver_id.company_ids:
                raise ValidationError(
                    _(
                        "%(approver)s is not allowed in task company %(company)s.",
                        approver=line.approver_id.display_name,
                        company=task_company.display_name,
                    )
                )

    def _is_approval_manager(self):
        return self.env.user.has_group(
            "project_task_approval_matrix.group_project_approval_manager"
        )

    def _workflow_write(self, values):
        """Write decision values from private task workflow methods only."""
        return super().write(values)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group(
            "project_task_approval_matrix.group_project_approval_manager"
        ):
            raise AccessError(_("Only Approval Managers may configure approval routes."))
        task_ids = {values.get("task_id") for values in vals_list if values.get("task_id")}
        tasks = self.env["project.task"].browse(task_ids)
        invalid = tasks.filtered(
            lambda task: not task.project_approval_enabled
            or task.approval_state not in EDITABLE_TASK_STATES
        )
        if invalid:
            raise UserError(
                _(
                    "Approval lines can only be added to enabled tasks in Draft, "
                    "Changes Requested, or Rejected status."
                )
            )
        clean_vals_list = []
        for original_values in vals_list:
            values = dict(original_values)
            supplied_state = values.pop("state", "waiting")
            if supplied_state != "waiting" or any(
                values.get(field_name)
                for field_name in (
                    "submitted_date",
                    "decision_date",
                    "decided_by_id",
                    "comments",
                )
            ):
                raise AccessError(
                    _("Approval decisions cannot be assigned while creating a route.")
                )
            values["state"] = "waiting"
            values.pop("submitted_date", None)
            values.pop("decision_date", None)
            values.pop("decided_by_id", None)
            values.pop("comments", None)
            clean_vals_list.append(values)
        lines = super().create(clean_vals_list)
        for task in lines.task_id:
            task._post_approval_audit(
                _("Approval route changed before submission.")
            )
        return lines

    def write(self, vals):
        if "task_id" in vals:
            raise AccessError(_("Approval lines cannot be moved to another task."))
        if set(vals) & DECISION_FIELDS:
            raise AccessError(_("Approval decisions can only be changed by workflow actions."))

        manager = self._is_approval_manager()
        if not manager and set(vals) - {"comments"}:
            raise AccessError(
                _("Approvers may only edit comments on their own pending step.")
            )
        if set(vals) & CONFIGURATION_FIELDS:
            if not manager:
                raise AccessError(_("Only Approval Managers may change approval routes."))
            if self.filtered(lambda line: line.task_id.approval_state not in EDITABLE_TASK_STATES):
                raise UserError(
                    _("Reset the approval workflow before changing its route.")
                )

        if "comments" in vals and not manager:
            forbidden = self.filtered(
                lambda line: line.state != "pending"
                or line.approver_id != self.env.user
            )
            if forbidden:
                raise AccessError(
                    _("You may only comment on your own pending approval step.")
                )
        result = super().write(vals)
        if set(vals) & CONFIGURATION_FIELDS:
            for task in self.task_id:
                task._post_approval_audit(
                    _("Approval route changed before submission.")
                )
        return result

    def unlink(self):
        if not self._is_approval_manager():
            raise AccessError(_("Only Approval Managers may change approval routes."))
        if self.filtered(lambda line: line.task_id.approval_state not in EDITABLE_TASK_STATES):
            raise UserError(_("Reset the approval workflow before changing its route."))
        tasks = self.task_id
        result = super().unlink()
        for task in tasks.exists():
            task._post_approval_audit(
                _("Approval route changed before submission.")
            )
        return result
