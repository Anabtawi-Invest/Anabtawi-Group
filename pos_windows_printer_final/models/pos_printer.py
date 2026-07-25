# -*- coding: utf-8 -*-
from odoo import fields, models, api

class PosPrinter(models.Model):
    _inherit = 'pos.printer'

    printer_type = fields.Selection(
        selection_add=[('cr_network_printer', 'Direct Network / Agent Printer')],
        ondelete={'cr_network_printer': 'set default'}
    )
    printer_id = fields.Many2one('printer.printer', string='Assigned Thermal Printer')

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_to_load = super()._load_pos_data_fields(config_id)
        # Keep Odoo's [] = "load all fields" contract intact.
        if not fields_to_load:
            return fields_to_load
        if 'printer_id' not in fields_to_load:
            fields_to_load.append('printer_id')
        return fields_to_load
