# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class Printer(models.Model):
    _name = "printer.printer"
    _description = "PoS Hardware Printers"
    _rec_name = "name"

    name = fields.Char(string="Printer Name", required=True)
    ip = fields.Char(string="IP Address / Hostname")
    port = fields.Integer(string="Port", default=80)
    printer_type = fields.Selection(
        [
            ("network", "IP / Network Printer (LAN)"),
            ("usb", "USB / Local Printer"),
        ],
        string="Printer Connection Type",
        default="network",
        required=True,
        help="Network printers communicate directly via ePOS over LAN IP. USB printers use direct local printing."
    )

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'name', 'ip', 'port', 'printer_type']

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []

    @api.model
    def _load_pos_data_search_read(self, data, config):
        domain = self._load_pos_data_domain(data, config)
        fields = self._load_pos_data_fields(config)
        return self.search_read(domain, fields, load=False)
