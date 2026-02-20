# -*- coding: utf-8 -*-
from odoo import models, fields


class PosConfig(models.Model):
    _inherit = 'pos.config'

    pledge_product_id = fields.Many2one(
        'product.product',
        string='Pledge Product',
        domain="[('sale_ok', '=', True)]",
        help='Product used to record pledge amount as a dedicated POS order line.',
    )
