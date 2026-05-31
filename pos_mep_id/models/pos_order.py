# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    mep_id = fields.Char(string="MEP ID")

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if "mep_id" not in fields_to_load:
            fields_to_load.append("mep_id")
        return fields_to_load
