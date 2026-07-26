# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    enable_custom_cake = fields.Boolean(
        string="Enable Custom Cake",
        default=True,
        help="Show Custom Cake and Cake Orders buttons in the Point of Sale.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if not fields_to_load:
            return fields_to_load
        if "enable_custom_cake" not in fields_to_load:
            fields_to_load.append("enable_custom_cake")
        return fields_to_load
