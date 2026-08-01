# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    cake_sugar_paste_product_id = fields.Many2one(
        "product.product",
        string="Sugar Paste Product",
    )
    cake_sugar_paste_qty = fields.Float(
        string="Sugar Paste Qty per Piece",
        default=1.0,
        help="Quantity of sugar paste used per cake piece in manufacturing.",
    )
    cake_sugar_paste_cost = fields.Float(
        string="Sugar Paste Unit Cost",
        digits="Product Price",
        help="Cost of one unit of sugar paste for price calculation.",
    )
    cake_cost_divisor = fields.Float(
        string="Cost Divisor",
        default=0.63,
        help="Selling price before tax = cost after overhead / this divisor.",
    )
    cake_overhead = fields.Float(
        string="Overhead (%)",
        default=0.0,
        help=(
            "Overhead percentage applied before the cost divisor. "
            "Example: 10%% divides total cost by 0.90 first, then by the cost divisor."
        ),
    )
    cake_tax_rate = fields.Float(
        string="Tax Rate (%)",
        default=16.0,
        help="Tax percentage applied on selling price before tax.",
    )
