# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_cake_order_for_pos_line(self, line):
        order = line.order_id
        if order.pos_cake_order_id:
            return order.pos_cake_order_id
        return self.env["pos.cake.order"].search(
            [("pos_order_id", "=", order.id)],
            limit=1,
        )

    def _prepare_stock_move_vals(self, first_line, order_lines):
        vals = super()._prepare_stock_move_vals(first_line, order_lines)
        move_value = 0.0
        has_cake = False
        for line in order_lines:
            cake_order = self._get_cake_order_for_pos_line(line)
            if cake_order:
                has_cake = True
                line_cost = cake_order.total_components_cost * abs(line.qty)
                move_value += line_cost
                _logger.info(
                    "[POS_CAKE_COGS] Move prep: POS order %s (id=%s), cake order %s, "
                    "product %s, qty=%s, component_cost=%s, line_cost=%s, "
                    "pos_cake_order_id=%s",
                    order.name if (order := line.order_id) else "?",
                    order.id if order else "?",
                    cake_order.name,
                    line.product_id.display_name,
                    line.qty,
                    cake_order.total_components_cost,
                    line_cost,
                    order.pos_cake_order_id.id if order and order.pos_cake_order_id else False,
                )
            else:
                move_value += line.product_id.standard_price * abs(line.qty)
        if has_cake:
            vals["pos_cake_move_value"] = move_value
            _logger.info(
                "[POS_CAKE_COGS] Move prep: product %s, total pos_cake_move_value=%s",
                first_line.product_id.display_name,
                move_value,
            )
        else:
            _logger.warning(
                "[POS_CAKE_COGS] Move prep: product %s, no cake order found for lines on "
                "POS orders %s — using standard_price (total=%s)",
                first_line.product_id.display_name,
                order_lines.mapped("order_id.name"),
                move_value,
            )
        return vals
