from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    purchase_receipt_same_month = fields.Boolean(
        string="Block Receipts Outside Purchase Order Month",
        help="When enabled, an incoming receipt linked to a purchase order can be "
        "validated only when the receipt validation date is in the same month and "
        "year as the purchase order confirmation date.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    purchase_receipt_same_month = fields.Boolean(
        related="company_id.purchase_receipt_same_month",
        readonly=False,
        string="Block Receipts Outside Purchase Order Month",
    )
