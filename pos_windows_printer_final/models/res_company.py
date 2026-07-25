# -*- coding: utf-8 -*-
from odoo import models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        if 'tax_calculation_rounding_method' not in fields:
            fields.append('tax_calculation_rounding_method')
        if 'currency_id' not in fields:
            fields.append('currency_id')
        return fields
