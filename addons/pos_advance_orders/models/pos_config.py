# -*- coding: utf-8 -*-
from odoo import models, fields

class PosConfig(models.Model):
    _inherit = "pos.config"

    advance_liability_account_id = fields.Many2one(
        "account.account",
        string="Advance Liability Account",
    )

    pledge_liability_account_id = fields.Many2one(
        "account.account",
        string="Pledge Liability Account",
    )

    advance_deposit_product_id = fields.Many2one(
        "product.product",
        string="Advance Deposit Product",
    )

    pledge_product_id = fields.Many2one(
        "product.product",
        string="Pledge Product",
    )

    discount_profile_id = fields.Many2one(
        "pos.discount.profile",
        string="Discount Profile",
    )

    discount_product_id = fields.Many2one(
        "product.product",
        string="Discount Product",
    )
