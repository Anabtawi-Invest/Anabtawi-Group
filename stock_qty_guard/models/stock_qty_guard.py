# -*- coding: utf-8 -*-
from odoo import models

"""
This module (Done > Demand) will run ONLY on Validate via stock.picking.button_validate()
To avoid conflicts, we disable @api.constrains that triggers on every save/write.
"""


class StockMove(models.Model):
    _inherit = "stock.move"


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"
