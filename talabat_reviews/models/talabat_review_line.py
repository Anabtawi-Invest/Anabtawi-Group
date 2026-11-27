# -*- coding: utf-8 -*-
from odoo import fields, models


class TalabatReviewLine(models.Model):
    _name = "talabat.review.line"
    _description = "Talabat Review Order Line"
    _order = "id"

    review_id = fields.Many2one(
        "talabat.review",
        required=True,
        ondelete="cascade",
        index=True,
    )
    store_id = fields.Many2one(related="review_id.store_id", store=True, index=True)
    pos_config_id = fields.Many2one(related="review_id.pos_config_id", store=True, index=True)
    rating = fields.Integer(related="review_id.rating", store=True, index=True)
    review_datetime = fields.Datetime(related="review_id.review_datetime", store=True, index=True)
    product_name = fields.Char(required=True, index=True)
    quantity = fields.Float(default=1.0)
    unit_price = fields.Float()
    product_id = fields.Many2one("product.product", string="Matched product")
