# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare

_ALLOWED_CODES = {"outgoing", "internal"}


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.constrains("quantity", "product_uom_qty", "picking_id")
    def _check_ops_done_not_over_demand(self):
        """Operations: يمنع Done(=quantity) أن يتجاوز Demand(=product_uom_qty)"""
        for move in self:
            if not move.picking_id or move.picking_type_id.code not in _ALLOWED_CODES:
                continue

            # في بيئتك Done على الـ move = field 'quantity'
            if float_compare(move.quantity or 0.0, move.product_uom_qty or 0.0,
                             precision_rounding=move.product_uom.rounding) > 0:
                raise ValidationError(_(
                    "ممنوع أن تكون الكمية المنجزة أكبر من الكمية المطلوبة.\n"
                    "المنتج: %(p)s\nالمطلوب: %(d)s %(u)s\nالمنجز: %(q)s %(u)s",
                    p=move.product_id.display_name,
                    d=move.product_uom_qty,
                    q=move.quantity,
                    u=move.product_uom.name,
                ))


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.constrains("qty_done", "move_id", "product_uom_id")
    def _check_detailed_done_not_over_demand(self):
        """Detailed Operations: مجموع qty_done لكل move لا يتجاوز demand"""
        for line in self:
            move = line.move_id
            if not move or not move.picking_id or move.picking_type_id.code not in _ALLOWED_CODES:
                continue

            done_total = 0.0
            for ml in move.move_line_ids.filtered(lambda x: x.state != "cancel"):
                done_total += ml.product_uom_id._compute_quantity(ml.qty_done, move.product_uom)

            if float_compare(done_total, move.product_uom_qty,
                             precision_rounding=move.product_uom.rounding) > 0:
                raise ValidationError(_(
                    "ممنوع أن يتجاوز مجموع الكمية المنجزة الكمية المطلوبة.\n"
                    "المنتج: %(p)s\nالمطلوب: %(d)s %(u)s\nمجموع المنجز: %(q)s %(u)s",
                    p=move.product_id.display_name,
                    d=move.product_uom_qty,
                    q=done_total,
                    u=move.product_uom.name,
                ))
