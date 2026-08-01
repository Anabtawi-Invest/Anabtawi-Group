# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cake_sugar_paste_product_id = fields.Many2one(
        related="company_id.cake_sugar_paste_product_id",
        readonly=False,
    )
    cake_sugar_paste_qty = fields.Float(
        related="company_id.cake_sugar_paste_qty",
        readonly=False,
    )
    cake_sugar_paste_cost = fields.Float(
        related="company_id.cake_sugar_paste_cost",
        readonly=False,
    )
    cake_cost_divisor = fields.Float(
        related="company_id.cake_cost_divisor",
        readonly=False,
    )
    cake_overhead = fields.Float(
        related="company_id.cake_overhead",
        readonly=False,
    )
    cake_tax_rate = fields.Float(
        related="company_id.cake_tax_rate",
        readonly=False,
    )
