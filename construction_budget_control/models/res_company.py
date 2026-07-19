from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    construction_gm_threshold = fields.Monetary(
        string="General Manager Approval Threshold",
        currency_field="currency_id",
        default=5000.0,
        help="Purchase Orders with an amount at or above this value require "
        "General Manager approval, after Accounting.",
    )
    construction_chairman_threshold = fields.Monetary(
        string="Chairman Approval Threshold",
        currency_field="currency_id",
        default=25000.0,
        help="Purchase Orders with an amount at or above this value require "
        "Chairman approval, after the General Manager.",
    )
