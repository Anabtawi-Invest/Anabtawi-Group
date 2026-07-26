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

            done_qty = move.quantity
            if not done_qty:
                continue

            on_hand_qty = move._get_physical_on_hand_qty(
                move.product_id, location, move.product_uom
            )

            if on_hand_qty - done_qty < 0 and cancel_backorder:
                allowed_qty = max(on_hand_qty, 0.0)
                if move.product_uom.compare(allowed_qty, move.quantity) < 0:
                    move.quantity = allowed_qty
                continue

            if on_hand_qty - done_qty < 0:
                raise UserError(_(
                    "❌ You cannot validate this Delivery Order.\n\n"
                    "Product: %s\n"
                    "Source Location: %s\n"
                    "Available Quantity: %s\n"
                    "Delivery Quantity: %s"
                ) % (
                    move.product_id.display_name,
                    location.display_name,
                    on_hand_qty,
                    done_qty,
                ))

        return super()._action_done(cancel_backorder)
