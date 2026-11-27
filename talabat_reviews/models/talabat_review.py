# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TalabatReview(models.Model):
    _name = "talabat.review"
    _description = "Talabat Customer Review"
    _order = "review_datetime desc, id desc"

    store_id = fields.Many2one(
        "talabat.store",
        required=True,
        ondelete="cascade",
        index=True,
    )
    pos_config_id = fields.Many2one(
        related="store_id.pos_config_id",
        store=True,
        index=True,
    )
    order_number = fields.Char(required=True, index=True)
    review_datetime = fields.Datetime(required=True, index=True)
    rating = fields.Integer(required=True, index=True)
    comment = fields.Text()
    can_reply = fields.Boolean(default=True)
    can_dispute = fields.Boolean(default=False)
    replied = fields.Boolean(default=False)
    disputed = fields.Boolean(default=False)
    awaiting_reply = fields.Boolean(compute="_compute_awaiting_reply", store=True)
    line_ids = fields.One2many("talabat.review.line", "review_id", string="Order products")
    line_count = fields.Integer(compute="_compute_line_count")
    external_uid = fields.Char(
        index=True,
        help="Stable key from Talabat when available; otherwise order_number+store.",
    )

    _sql_constraints = [
        (
            "store_order_uniq",
            "unique(store_id, order_number)",
            "A review for this store and order already exists.",
        ),
    ]

    @api.depends("can_reply", "replied")
    def _compute_awaiting_reply(self):
        for review in self:
            review.awaiting_reply = bool(review.can_reply and not review.replied)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for review in self:
            review.line_count = len(review.line_ids)

    @api.model
    def rating_band(self, rating):
        if rating <= 2:
            return "low"
        if rating >= 4:
            return "high"
        return "mid"
