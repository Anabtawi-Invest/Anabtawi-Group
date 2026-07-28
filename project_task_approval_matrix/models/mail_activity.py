from odoo import fields, models


class MailActivity(models.Model):
    _inherit = "mail.activity"

    project_task_approval_line_id = fields.Many2one(
        "project.task.approval.line",
        string="Task Approval Line",
        ondelete="cascade",
        copy=False,
        index=True,
    )
