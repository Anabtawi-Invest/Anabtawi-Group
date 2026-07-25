# -*- coding: utf-8 -*-
from odoo import fields, models, api

class PosPrinter(models.Model):
    _inherit = 'pos.printer'

    printer_type = fields.Selection(selection_add=[('cr_network_printer', 'Direct Network / Agent Printer')])
    printer_id = fields.Many2one('printer.printer', string='Assigned Thermal Printer')

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        params.append('printer_id')
        return params
