# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_physical_on_hand_qty(self, product, location, product_uom):
        """Return pure on-hand quantity (sum of quant.quantity) in move UoM.

        This intentionally ignores reserved/forecast values.
        """
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id', 'child_of', location.id),
        ])
        on_hand_product_uom = sum(quants.mapped('quantity'))
        return product.uom_id._compute_quantity(
            on_hand_product_uom, product_uom, round=False
        )

    def _action_done(self, cancel_backorder=False):

        for move in self:
            location = move.location_id

            if not location or not location.restrict_negative:
                continue

            picking = move.picking_id
            if not picking:
                continue

            if picking.picking_type_id.code == 'incoming':
                continue

            if picking.picking_type_id.code != 'internal':
                continue

            done_qty = move.quantity
            if not done_qty:
                continue

            on_hand_qty = move._get_physical_on_hand_qty(
                move.product_id, location, move.product_uom
            )

            qty_after = on_hand_qty - done_qty

            # 6️⃣ In "No Backorder" flow, trim done qty to available qty.
            # This keeps negative stock blocked while allowing validation without creating backorder.
            if qty_after < 0 and cancel_backorder:
                allowed_qty = max(on_hand_qty, 0.0)
                if move.product_uom.compare(allowed_qty, move.quantity) < 0:
                    move.quantity = allowed_qty
                continue

            if qty_after < 0:
                raise UserError(_(
                    "You cannot validate this Internal Transfer.\n\n"
                    "Product: %s\n"
                    "Source Location: %s\n"
                    "Available Quantity: %s\n"
                    "Requested Quantity: %s"
                ) % (
                    move.product_id.display_name,
                    location.display_name,
                    on_hand_qty,
                    done_qty,
                ))

        # إذا لم يحدث منع → نكمل التنفيذ
        return super()._action_done(cancel_backorder)
