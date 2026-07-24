# -*- coding: utf-8 -*-
# Part of Creyox Technologies

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    printer_id = fields.Many2one('printer.printer', string='Printer')

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        if fields:
            fields.append('printer_id')
        return fields
