from odoo import fields, models


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    use_sick_fallback = fields.Boolean(
        string="Use Sick Fallback",
        help="If enabled, requests of this type are automatically redirected to Sick/Annual/Unpaid based on balances.",
    )
