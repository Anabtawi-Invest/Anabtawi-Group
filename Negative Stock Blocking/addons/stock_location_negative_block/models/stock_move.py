# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder)

        StockQuant = self.env['stock.quant']

        for move in self:
            # نتحقق فقط من الموقع المصدر
            location = move.location_id
            if not location or not location.restrict_negative:
                continue

            # ✅ السماح دائمًا بالاستلام (Purchase Receipts)
            if move.picking_type_id and move.picking_type_id.code == 'incoming':
                continue

            # 🔒 نمنع فقط:
            # 1) Internal Transfers
            is_internal = bool(
                move.picking_type_id and move.picking_type_id.code == 'internal'
            )

            # 2) Inventory Adjustments
            is_inventory_adjustment = bool(move.inventory_id)

            if not (is_internal or is_inventory_adjustment):
                continue

            # بعد تنفيذ الحركة نتحقق من الكمية المتاحة
            available_qty = StockQuant._get_available_quantity(
                move.product_id, location
            )

            if available_qty < 0:
                raise UserError(_(
                    "Negative stock is not allowed in location '%s' for product '%s'."
                ) % (location.display_name, move.product_id.display_name))

        return res
