# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    required_id_number = fields.Boolean(string="Required ID Number")

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if "required_id_number" not in fields_to_load:
            fields_to_load.append("required_id_number")
        return fields_to_load