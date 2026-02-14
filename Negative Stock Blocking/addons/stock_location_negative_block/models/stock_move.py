# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):

        for move in self:
            location = move.location_id

            # 1️⃣ لا يوجد موقع أو لا يوجد تقييد
            if not location or not location.restrict_negative:
                continue

            picking = move.picking_id
            if not picking:
                continue

            # 2️⃣ اسمح دائمًا بالـ Incoming (PO Receipt)
            if picking.picking_type_id.code == 'incoming':
                continue

            # 3️⃣ نطبق المنع فقط على Internal Transfer
            if picking.picking_type_id.code != 'internal':
                continue

            # 4️⃣ الكمية المنفذة (بوحدة move.product_uom)
            done_qty = move.quantity
            if not done_qty:
                continue

            # 5️⃣ الكمية المتاحة قبل التنفيذ
            available_qty_product_uom = self.env['stock.quant']._get_available_quantity(
                move.product_id, location
            )
            available_qty = move.product_id.uom_id._compute_quantity(
                available_qty_product_uom, move.product_uom, round=False
            )

            qty_after = available_qty - done_qty

            # 6️⃣ In "No Backorder" flow, trim done qty to available qty.
            # This keeps negative stock blocked while allowing validation without creating backorder.
            if qty_after < 0 and cancel_backorder:
                allowed_qty = max(available_qty, 0.0)
                if move.product_uom.compare(allowed_qty, move.quantity) < 0:
                    move.quantity = allowed_qty
                continue

            # 6️⃣ المنع مع رسالة واضحة
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
                    available_qty,
                    done_qty,
                ))

        # إذا لم يحدث منع → نكمل التنفيذ
        return super()._action_done(cancel_backorder)
