# -*- coding: utf-8 -*-
from odoo import fields, models, api

class PosConfig(models.Model):
    _inherit = 'pos.config'

    direct_printer_id = fields.Many2one(
        'printer.printer', 
        string='Direct Branch Printer', 
        help='Assigned receipt thermal printer for this POS configuration.'
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        params.append('direct_printer_id')
        return params
