# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    pos_cake_order_id = fields.Many2one(
        "pos.cake.order",
        string="Custom Cake Order",
        readonly=True,
        copy=False,
    )

    def action_pos_order_paid(self):
        for order in self:
            if order.pos_cake_order_id:
                _logger.info(
                    "[POS_CAKE_COGS] Paid order %s linked to cake order %s, "
                    "total_components_cost=%s, product=%s",
                    order.name,
                    order.pos_cake_order_id.name,
                    order.pos_cake_order_id.total_components_cost,
                    order.pos_cake_order_id.product_id.display_name,
                )
            else:
                cake_lines = order.lines.filtered(
                    lambda line: line.product_id.display_name
                )
                if cake_lines:
                    _logger.warning(
                        "[POS_CAKE_COGS] Paid order %s has no pos_cake_order_id. Lines: %s",
                        order.name,
                        [
                            (line.product_id.display_name, line.price_unit, line.qty)
                            for line in cake_lines
                        ],
                    )
        result = super().action_pos_order_paid()
        for order in self.filtered(lambda o: o.pos_cake_order_id):
            if order.state == "paid" and order.pos_cake_order_id.state != "paid":
                order.pos_cake_order_id.sudo().action_mark_paid(order)
        return result

    @api.model
    def _order_fields(self, ui_order):
        vals = super()._order_fields(ui_order)
        cake_order_id = ui_order.get("pos_cake_order_id")
        if cake_order_id:
            vals["pos_cake_order_id"] = int(cake_order_id)
        return vals


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    def _compute_total_cost(self, stock_moves):
        cake_lines = self.filtered(lambda line: line.order_id.pos_cake_order_id)
        for line in cake_lines:
            line.total_cost = (
                line.order_id.pos_cake_order_id.total_components_cost * abs(line.qty)
            )
            line.is_total_cost_computed = True
        return super(PosOrderLine, self - cake_lines)._compute_total_cost(stock_moves)
