from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    extra_hours_leave_type_id = fields.Many2one(
        "hr.leave.type",
        related="company_id.extra_hours_leave_type_id",
        readonly=False,
    )
    annual_leave_type_id = fields.Many2one(
        "hr.leave.type",
        related="company_id.annual_leave_type_id",
        readonly=False,
    )
    unpaid_leave_type_id = fields.Many2one(
        "hr.leave.type",
        related="company_id.unpaid_leave_type_id",
        readonly=False,
    )
