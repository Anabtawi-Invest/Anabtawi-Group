# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    pos_cake_move_value = fields.Float(
        string="Custom Cake Move Value",
        copy=False,
        help="Component cost captured at POS picking creation for custom cake orders.",
    )

    def _set_value(self, correction_quantity=None):
        cake_moves = self.filtered(lambda move: move.pos_cake_move_value)
        regular_moves = self - cake_moves

        for move in cake_moves:
            if correction_quantity:
                previous_qty = move.quantity - correction_quantity
                ratio = correction_quantity / previous_qty if previous_qty else 0
                move.value += ratio * move.value
                _logger.info(
                    "[POS_CAKE_COGS] Value correction: move %s, ratio=%s, value=%s",
                    move.id,
                    ratio,
                    move.value,
                )
            else:
                move.value = move.pos_cake_move_value
                _logger.info(
                    "[POS_CAKE_COGS] Value set: move %s, product %s, "
                    "pos_cake_move_value=%s, move.value=%s, price_unit=%s",
                    move.id,
                    move.product_id.display_name,
                    move.pos_cake_move_value,
                    move.value,
                    move._get_price_unit(),
                )

        if regular_moves:
            return super(StockMove, regular_moves)._set_value(correction_quantity)
        return None
