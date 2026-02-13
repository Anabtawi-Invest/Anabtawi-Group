from odoo import models, fields

class ResCompany(models.Model):
    _inherit = "res.company"

    lateness_annual_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Annual Leave Type for Lateness (Hours)",
        help="Hour-based Annual Leave type that will be consumed when overtime is not enough to cover lateness.",
    )
