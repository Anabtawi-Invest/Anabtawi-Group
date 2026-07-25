# -*- coding: utf-8 -*-
from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_direct_printer_id = fields.Many2one(
        related='pos_config_id.direct_printer_id',
        readonly=False,
        string='Direct Branch Printer'
    )
