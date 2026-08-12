# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    has_pledge = fields.Boolean(related="product_tmpl_id.has_pledge", readonly=False)
    pledge_amount = fields.Monetary(
        related="product_tmpl_id.pledge_amount",
        currency_field="pledge_currency_id",
        readonly=False,
    )
    pledge_currency_id = fields.Many2one(
        related="product_tmpl_id.pledge_currency_id",
        readonly=True,
    )
