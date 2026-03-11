# -*- coding: utf-8 -*-
from odoo import models, api, fields, _




class PosOrder(models.Model):
    _inherit = 'product.pricelist'
    required_id_number = fields.Boolean(string="Required ID Number")

