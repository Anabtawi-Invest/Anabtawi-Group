# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TalabatStore(models.Model):
    _name = "talabat.store"
    _description = "Talabat Store"
    _order = "name"

    name = fields.Char(required=True, index=True)
    vendor_id = fields.Char(
        string="Talabat Vendor ID",
        required=True,
        index=True,
        help="Vendor code from the partner portal URL, e.g. TB_JO;629658",
    )
    pos_config_id = fields.Many2one(
        "pos.config",
        string="POS Branch",
        index=True,
        help="Maps this Talabat outlet to a POS branch on the Executive Dashboard.",
    )
    active = fields.Boolean(default=True)
    store_rating = fields.Float(digits=(16, 1), readonly=True)
    review_count = fields.Integer(readonly=True)
    one_star_count = fields.Integer(string="1-star ratings", readonly=True)
    star_5_count = fields.Integer(readonly=True)
    star_4_count = fields.Integer(readonly=True)
    star_3_count = fields.Integer(readonly=True)
    star_2_count = fields.Integer(readonly=True)
    star_1_count = fields.Integer(readonly=True)
    summary_text = fields.Text(string="Reviews summary", readonly=True)
    last_sync_at = fields.Datetime(readonly=True)
    review_ids = fields.One2many("talabat.review", "store_id", string="Reviews")
    review_ids_count = fields.Integer(compute="_compute_review_ids_count")

    _sql_constraints = [
        ("vendor_id_uniq", "unique(vendor_id)", "Talabat vendor ID must be unique."),
    ]

    @api.depends("review_ids")
    def _compute_review_ids_count(self):
        for store in self:
            store.review_ids_count = len(store.review_ids)

    def action_open_reviews(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "talabat.review",
            "view_mode": "list,form",
            "domain": [("store_id", "=", self.id)],
            "context": {"default_store_id": self.id},
        }

    @api.model
    def cron_sync_reviews(self):
        return self.env["talabat.sync.mixin"].cron_sync_reviews()

    @api.model
    def action_sync_reviews_now(self):
        return self.env["talabat.sync.mixin"].sync_reviews(fetch_order_lines=True)
