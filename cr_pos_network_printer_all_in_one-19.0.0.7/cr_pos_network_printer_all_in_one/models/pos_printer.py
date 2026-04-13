# -*- coding: utf-8 -*-
# Part of Creyox Technologies

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class PosPrinter(models.Model):
    _inherit = 'pos.printer'

    printer_type = fields.Selection(selection_add=[('cr_network_printer', 'Use a custom printer')])
    printer_id = fields.Many2one('printer.printer', string='Printer')

    @api.constrains('cr_network_printer_ip')
    def _constrains_cr_network_printer_ip(self):
        for record in self:
            if record.printer_type == 'cr_network_printer' and not record.cr_network_printer_ip:
                raise ValidationError(_("Custom Network Printer IP Address cannot be empty."))

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        params += ['printer_id']
        return params
