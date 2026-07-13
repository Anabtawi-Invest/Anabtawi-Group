# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    cost_price = fields.Float(
        string='Cost',
        compute='_compute_cost_and_margin',
        store=True,
        digits='Product Price',
        help="Product cost (Cost field on the product) multiplied by the "
             "quantity sold on this order line.",
    )
    margin = fields.Float(
        string='Margin',
        compute='_compute_cost_and_margin',
        store=True,
        digits='Product Price',
        help="Untaxed sales amount of this line minus its Cost.",
    )
    margin_percent = fields.Float(
        string='Margin %',
        compute='_compute_cost_and_margin',
        store=True,
        digits=(16, 2),
        help="Margin divided by the untaxed sales amount, expressed as a percentage.",
    )

    @api.depends('qty', 'price_subtotal', 'product_id', 'product_id.standard_price')
    def _compute_cost_and_margin(self):
        for line in self:
            unit_cost = line.product_id.standard_price or 0.0
            line.cost_price = unit_cost * line.qty
            line.margin = line.price_subtotal - line.cost_price
            line.margin_percent = (
                (line.margin / line.price_subtotal) * 100.0
                if line.price_subtotal
                else 0.0
            )
