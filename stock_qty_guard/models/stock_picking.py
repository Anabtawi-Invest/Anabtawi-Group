# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

_ALLOWED_CODES = {"incoming", "outgoing", "internal"}


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        # ✅ Done > Demand check (Validate-only)
        for picking in self:
            if not picking.picking_type_id or picking.picking_type_id.code not in _ALLOWED_CODES:
                continue

            for move in picking.move_ids:
                if move.state == "cancel":
                    continue

                demand = move.product_uom_qty or 0.0

                # Sum qty_done from move lines converted to move UoM
                done_lines = 0.0
                for ml in move.move_line_ids.filtered(lambda l: l.state != "cancel"):
                    if not ml.qty_done:
                        continue
                    done_lines += ml.product_uom_id._compute_quantity(ml.qty_done, move.product_uom)

                # Some DBs use move.quantity as done
                done_move = move.quantity or 0.0

                # Use max to avoid sync timing issues between move and move lines
                done_total = max(done_lines, done_move)

                if float_compare(
                    done_total, demand,
                    precision_rounding=move.product_uom.rounding
                ) > 0:
                    raise UserError(_(
                        "ممنوع أن تكون الكمية المنجزة أكبر من الكمية المطلوبة.\n\n"
                        "المنتج: %(p)s\n"
                        "المطلوب: %(d)s %(u)s\n"
                        "المنجز: %(q)s %(u)s"
                    ) % {
                        "p": move.product_id.display_name,
                        "d": demand,
                        "q": done_total,
                        "u": move.product_uom.name,
                    })

        return super().button_validate()
