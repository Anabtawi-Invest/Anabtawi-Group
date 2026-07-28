# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_pos_order_lines_for_move(self):
        self.ensure_one()
        lines = self.env["pos.order.line"]
        picking = self.picking_id
        if not picking:
            return lines

        if picking.pos_order_id:
            return picking.pos_order_id.lines.filtered(
                lambda line: line.product_id == self.product_id
            )

        if picking.pos_session_id:
            for order in picking.pos_session_id.order_ids:
                lines |= order.lines.filtered(
                    lambda line: line.product_id == self.product_id
                )
        return lines

    def _has_pos_cake_lines(self):
        self.ensure_one()
        return any(
            line.order_id.pos_cake_order_id for line in self._get_pos_order_lines_for_move()
        )

    def _get_pos_cake_move_value(self):
        """Value outgoing POS moves using cake component costs where applicable."""
        self.ensure_one()
        total = 0.0
        for line in self._get_pos_order_lines_for_move():
            if line.order_id.pos_cake_order_id:
                total += line.order_id.pos_cake_order_id.total_components_cost * abs(line.qty)
            else:
                total += line.product_id.standard_price * abs(line.qty)
        return total

    def _set_value(self, correction_quantity=None):
        cake_moves = self.filtered(
            lambda move: move._is_out() and move.picking_id and move._has_pos_cake_lines()
        )
        regular_moves = self - cake_moves

        for move in cake_moves:
            if correction_quantity:
                previous_qty = move.quantity - correction_quantity
                ratio = correction_quantity / previous_qty if previous_qty else 0
                move.value += ratio * move.value
            else:
                move.value = move._get_pos_cake_move_value()

        if regular_moves:
            return super(StockMove, regular_moves)._set_value(correction_quantity)
        return None
