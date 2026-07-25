# -*- coding: utf-8 -*-
from odoo import models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_to_load = super()._load_pos_data_fields(config_id)
        # Keep Odoo's [] = "load all fields" contract intact.
        if not fields_to_load:
            return fields_to_load
        if 'tax_calculation_rounding_method' not in fields_to_load:
            fields_to_load.append('tax_calculation_rounding_method')
        return fields_to_load
