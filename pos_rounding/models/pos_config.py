# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    discount_adjustment_product_id = fields.Many2one(
        "product.product",
        string="Rounding Adjustment",
        domain=[("sale_ok", "=", True)],
        help="Product used to record pledge amount as a POS sale line. Its income account should be a liability.",
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

class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_pos_config(self):
        res = super()._loader_params_pos_config()
        res["search_params"]["fields"].append("discount_adjustment_product_id")
        return res