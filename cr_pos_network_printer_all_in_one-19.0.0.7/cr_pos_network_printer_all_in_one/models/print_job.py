# -*- coding: utf-8 -*-
# Part of Creyox Technologies

from odoo import models, fields, api


class PrintJob(models.Model):
    _inherit = 'print.job'

    ip = fields.Char(string='Printer IP')
    port = fields.Integer(string='Printer Port', default=9100)
    is_open_cashbox = fields.Boolean(string='Is Open Cash Drawer?', default=False)
    printer_type = fields.Selection([('network', 'IP/Network Printer'), ('usb', 'USB Printer')], string='Printer Type')
 