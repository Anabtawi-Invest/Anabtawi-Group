# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):

        for move in self:
            location = move.location_id
            if not location or not location.restrict_negative:
                continue

            picking = move.picking_id
            if not picking:
                continue

            # 🔹 Only apply to outgoing pickings
            if picking.picking_type_id.code != 'outgoing':
                continue

            # 🔹 Skip ALL return pickings (correct detection)
            if any(m.origin_returned_move_id for m in picking.move_ids):
                continue

            # 🔹 Skip vendor returns (extra safety)
            if picking.location_dest_id.usage == 'supplier':
                continue

            done_qty = sum(move.move_line_ids.mapped('quantity'))
            if not done_qty:
                continue

            available_qty = self.env['stock.quant']._get_available_quantity(
                move.product_id, location
            )

            if available_qty - done_qty < 0:
                raise UserError(_(
                    "❌ You cannot validate this Delivery Order.\n\n"
                    "Product: %s\n"
                    "Source Location: %s\n"
                    "Available Quantity: %s\n"
                    "Delivery Quantity: %s"
                ) % (
                    move.product_id.display_name,
                    location.display_name,
                    available_qty,
                    done_qty,
                ))

        return super()._action_done(cancel_backorder)
