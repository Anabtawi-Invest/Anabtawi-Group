# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder)

        StockQuant = self.env['stock.quant']

        for move in self:
            location = move.location_id
            if not location or not location.restrict_negative:
                continue

            # ✅ السماح دائمًا بالاستلام (PO / Incoming)
            if move.picking_id and move.picking_type_id.code == 'incoming':
                continue

            # 🔒 Internal Transfer
            is_internal = bool(
                move.picking_id and move.picking_type_id.code == 'internal'
            )

            # 🔒 Inventory Adjustment (Odoo 19 الصحيح)
            is_inventory_adjustment = not move.picking_id

            if not (is_internal or is_inventory_adjustment):
                continue

            available_qty = StockQuant._get_available_quantity(
                move.product_id, location
            )

            if available_qty < 0:
                raise UserError(_(
                    "Negative stock is not allowed in location '%s' for product '%s'."
                ) % (location.display_name, move.product_id.display_name))

        return res
