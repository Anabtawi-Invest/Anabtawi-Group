# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    cake_order_ids = fields.One2many(
        "pos.cake.order",
        "production_id",
        string="Custom Cake Orders",
    )
    is_custom_cake = fields.Boolean(
        string="Is Custom Cake",
        compute="_compute_is_custom_cake",
    )
    custom_cake_note = fields.Text(string="Custom Cake Note", copy=False)
    custom_cake_image_ids = fields.One2many(
        "pos.cake.image",
        "production_id",
        string="Custom Cake Images",
    )

    @api.depends("cake_order_ids")
    def _compute_is_custom_cake(self):
        for production in self:
            production.is_custom_cake = bool(production.cake_order_ids)
