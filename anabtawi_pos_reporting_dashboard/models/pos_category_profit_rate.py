# -*- coding: utf-8 -*-
from odoo import fields, models


class PosCategoryProfitRate(models.Model):
    """Percentage applied to a POS category when studying category profit.

    150 means the product cost is multiplied by 1.50.
    """

    _name = "pos.category.profit.rate"
    _description = "POS Category Percentage"
    _order = "pos_categ_id"
    _rec_name = "pos_categ_id"

    pos_categ_id = fields.Many2one(
        "pos.category",
        string="POS Category",
        required=True,
        ondelete="cascade",
        index=True,
    )
    percentage = fields.Float(
        string="Percentage",
        required=True,
        digits=(16, 2),
        help="150 means the cost is multiplied by 1.50. "
             "Category profit is untaxed sales minus cost times this percentage. "
             "If a category has no percentage, full cost is used (sales − cost).",
    )

    _pos_categ_uniq = models.Constraint(
        "unique(pos_categ_id)",
        "This POS category already has a percentage.",
    )
