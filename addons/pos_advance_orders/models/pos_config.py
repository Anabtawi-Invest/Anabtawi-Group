from odoo import models, fields

class PosConfig(models.Model):
    _inherit = "pos.config"

    # --- Advance & Pledge Liability Configuration ---
    advance_liability_account_id = fields.Many2one(
        "account.account",
        string="Advance Liability Account",
        help="Account used for Customer Advances Liability"
    )

    pledge_liability_account_id = fields.Many2one(
        "account.account",
        string="Pledge Liability Account",
        help="Account used for Customer Plate Deposits"
    )

    advance_deposit_product_id = fields.Many2one(
        "product.product",
        string="Advance Deposit Product"
    )

    pledge_product_id = fields.Many2one(
        "product.product",
        string="Pledge Product"
    )

    # --- Discount Profile Configuration ---
    discount_profile_id = fields.Many2one(
        "pos.discount.profile",
        string="Discount Profile",
    )

    discount_product_id = fields.Many2one(
        "product.product",
        string="Discount Product",
        help="Service product, no tax. Used to post discount as a negative line.",
    )
