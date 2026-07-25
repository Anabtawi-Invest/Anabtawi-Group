# -*- coding: utf-8 -*-
from odoo import fields, models, api

class PosConfig(models.Model):
    _inherit = 'pos.config'

    direct_printer_id = fields.Many2one(
        'printer.printer',
        string='Direct Branch Printer',
        help='Assigned thermal printer (Windows Host, LAN, USB, Bluetooth) for this POS session.'
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        if 'direct_printer_id' not in params:
            params.append('direct_printer_id')
        if 'use_pricelist' not in params:
            params.append('use_pricelist')
        return params
