from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    extra_hours_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Fallback Extra Hours Leave Type",
    )
    annual_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Fallback Annual Leave Type",
    )
    unpaid_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Fallback Unpaid Leave Type",
    )
