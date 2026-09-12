# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    custom_cake_note = fields.Text(string="Custom Cake Note", copy=False)
