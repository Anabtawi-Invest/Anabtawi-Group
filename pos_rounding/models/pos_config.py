# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    discount_adjustment_product_id = fields.Many2one(
        "product.product",
        string="Rounding Adjustment",
        domain=[("sale_ok", "=", True)],
        help="Product used to determine the account for Open Amount adjustments. Its income account should point to the target liability/adjustment account.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        """Expose discount_adjustment_product_id to POS frontend data."""
        fields_to_load = super()._load_pos_data_fields(config)
        # In core POS, empty list means "load all fields"; keep it unchanged.
        if not fields_to_load:
            return fields_to_load
        if "discount_adjustment_product_id" not in fields_to_load:
            fields_to_load.append("discount_adjustment_product_id")
        return fields_to_load