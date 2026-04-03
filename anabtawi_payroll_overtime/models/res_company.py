from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    overtime_hourly_amount = fields.Float(
        string="Overtime Hourly Amount",
        default=0.0,
        help="Amount to pay per extra hour when quantity-based overtime input is used.",
    )
