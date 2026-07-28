from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class ProjectProject(models.Model):
    _inherit = "project.project"

    approval_matrix_enabled = fields.Boolean(
        string="Use Task Approval Matrix",
        default=False,
        tracking=True,
        copy=True,
    )
    prevent_task_completion_without_approval = fields.Boolean(
        string="Block Task Completion Before Approval",
        default=True,
        tracking=True,
        copy=True,
    )
    prevent_self_approval = fields.Boolean(
        string="Prevent Task Assignee Self-Approval",
        default=True,
        tracking=True,
        copy=True,
    )
    send_approval_email_notifications = fields.Boolean(
        string="Send Approval Email Notifications",
        default=False,
        tracking=True,
        copy=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        protected = {
            "approval_matrix_enabled",
            "prevent_task_completion_without_approval",
            "prevent_self_approval",
            "send_approval_email_notifications",
        }
        defaults = self.default_get(list(protected))
        non_default_configuration = any(
            any(
                field_name in values
                and values[field_name]
                != defaults.get(field_name)
                for field_name in protected
            )
            for values in vals_list
        )
        if non_default_configuration and not self.env.user.has_group(
            "project_task_approval_matrix.group_project_approval_manager"
        ):
            raise AccessError(
                _("Only Approval Managers may configure project approvals.")
            )
        return super().create(vals_list)

    def write(self, values):
        approval_settings = {
            "approval_matrix_enabled",
            "prevent_task_completion_without_approval",
            "prevent_self_approval",
            "send_approval_email_notifications",
        }
        if approval_settings & set(values) and not self.env.user.has_group(
            "project_task_approval_matrix.group_project_approval_manager"
        ):
            raise AccessError(
                _("Only Approval Managers may change project approval settings.")
            )

        disabling = self.filtered("approval_matrix_enabled") if values.get(
            "approval_matrix_enabled"
        ) is False else self.env["project.project"]
        for project in disabling:
            for task in project.tasks.filtered(
                lambda record: record.approval_required
                and record.approval_state in ("submitted", "partially_approved")
            ):
                lines = task._approval_lines_sudo()
                task._close_line_activities(
                    lines, _("Project approval matrix disabled")
                )
                lines.filtered(
                    lambda line: line.state in ("waiting", "pending")
                )._workflow_write({"state": "cancelled"})
                task.sudo()._approval_workflow_write(
                    {
                        "approval_state": "draft",
                        "submitted_by_id": False,
                        "submitted_date": False,
                        "approved_date": False,
                    }
                )
                task._post_approval_audit(
                    _("Approval round reset because the project matrix was disabled.")
                )
        return super().write(values)
