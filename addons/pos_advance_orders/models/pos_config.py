from odoo import models, fields

class PosConfig(models.Model):
    _inherit = "pos.config"

    advance_liability_account_id = fields.Many2one(
        "account.account",
        string="Advance Liability Account",
        help="Customer Advances Liability"
    )

    pledge_liability_account_id = fields.Many2one(
        "account.account",
        string="Pledge Liability Account",
        help="Customer Plate Deposits"
    )

    advance_deposit_product_id = fields.Many2one(
        "product.product",
        string="Advance Deposit Product"
    )

    pledge_product_id = fields.Many2one(
        "product.product",
        string="Pledge Product"
    )
