from odoo import fields, models


class ProjectTaskType(models.Model):
    _inherit = "project.task.type"

    approval_closing_stage = fields.Boolean(
        string="Approval Closing Stage",
        help=(
            "Tasks requiring approval cannot be moved to this stage until all "
            "required approvals are approved."
        ),
    )
