# -*- coding: utf-8 -*-
from odoo import fields, models

class PosConfig(models.Model):
    _inherit = 'pos.config'

    printer_id = fields.Many2one('printer.printer', string='Receipt Printer', help='Assigned receipt thermal printer for this POS configuration.')
