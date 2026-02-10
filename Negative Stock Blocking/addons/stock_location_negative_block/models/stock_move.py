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

            # ✅ السماح دائمًا بالاستلام
            if move.picking_id and move.picking_type_id.code == 'incoming':
                continue

            # 🔒 Internal Transfer
            is_internal = bool(
                move.picking_id and move.picking_type_id.code == 'internal'
            )

            # 🔒 Inventory Adjustment
            is_inventory_adjustment = not move.picking_id

            if not (is_internal or is_inventory_adjustment):
                continue

            # 🔥 الحساب الصحيح
            available_qty = self.env['stock.quant']._get_available_quantity(
                move.product_id, location
            )

            qty_after_move = available_qty - move.quantity_done

            if qty_after_move < 0:
                raise UserError(_(
                    "Negative stock is not allowed in location '%s' for product '%s'.\n"
                    "Available: %s, Requested: %s"
                ) % (
                    location.display_name,
                    move.product_id.display_name,
                    available_qty,
                    move.quantity_done,
                ))

        # ننفذ الحركة فقط إذا لم يُرفع خطأ
        return super()._action_done(cancel_backorder)
