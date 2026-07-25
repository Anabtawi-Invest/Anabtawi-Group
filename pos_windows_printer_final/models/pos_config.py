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
        fields_to_load = super()._load_pos_data_fields(config_id)
        # Odoo 19 uses an empty list as the sentinel for "load all fields".
        # Converting [] into a partial list drops company_id/currency_id and
        # breaks the POS tax engine during order setup.
        if not fields_to_load:
            return fields_to_load
        if 'direct_printer_id' not in fields_to_load:
            fields_to_load.append('direct_printer_id')
        return fields_to_load
