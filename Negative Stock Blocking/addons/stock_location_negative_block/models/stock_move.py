# -*- coding: utf-8 -*-
from odoo import models

""" 
Negative stock is enforced in stock.picking.button_validate().
This override is kept as pass-through to avoid double checks and side-effects.
"""


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        return super()._action_done(cancel_backorder=cancel_backorder)
