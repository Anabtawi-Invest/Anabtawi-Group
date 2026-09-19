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

    def _get_linked_cake_product_lines(self):
        """Return order lines that match the linked cake product."""
        self.ensure_one()
        cake_order = self.pos_cake_order_id
        if not cake_order or not cake_order.product_id:
            return self.env["pos.order.line"]
        return self.lines.filtered(lambda line: line.product_id == cake_order.product_id)

    def _has_linked_cake_product(self):
        self.ensure_one()
        return bool(self._get_linked_cake_product_lines())

    def _clear_invalid_cake_link(self):
        """Drop cake link when the ticket no longer contains the cake product."""
        for order in self.filtered("pos_cake_order_id"):
            if order._has_linked_cake_product():
                continue
            _logger.warning(
                "[POS_CAKE] Clearing invalid cake link on POS order %s (was %s). "
                "Ticket products: %s",
                order.name,
                order.pos_cake_order_id.name,
                [(line.product_id.display_name, line.qty) for line in order.lines],
            )
            order.pos_cake_order_id = False

    def action_pos_order_paid(self):
        for order in self:
            if order.pos_cake_order_id:
                _logger.info(
                    "[POS_CAKE_COGS] Paid order %s linked to cake order %s, "
                    "total_components_cost=%s, product=%s, has_cake_line=%s",
                    order.name,
                    order.pos_cake_order_id.name,
                    order.pos_cake_order_id.total_components_cost,
                    order.pos_cake_order_id.product_id.display_name,
                    order._has_linked_cake_product(),
                )
        self._clear_invalid_cake_link()
        result = super().action_pos_order_paid()
        for order in self.filtered(lambda o: o.pos_cake_order_id):
            if (
                order.state == "paid"
                and order.pos_cake_order_id.state != "paid"
                and order._has_linked_cake_product()
            ):
                order.pos_cake_order_id.sudo().action_mark_paid(order)
            elif order.pos_cake_order_id and not order._has_linked_cake_product():
                _logger.warning(
                    "[POS_CAKE] Not marking cake %s as paid from POS order %s: "
                    "cake product is missing from the ticket.",
                    order.pos_cake_order_id.name,
                    order.name,
                )
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
        # Apply cake component cost only to the cake product line, not every line
        # on a ticket that happens to be linked to a cake order.
        cake_product_lines = self.filtered(
            lambda line: (
                line.order_id.pos_cake_order_id
                and line.order_id.pos_cake_order_id.product_id
                and line.product_id == line.order_id.pos_cake_order_id.product_id
            )
        )
        for line in cake_product_lines:
            line.total_cost = (
                line.order_id.pos_cake_order_id.total_components_cost * abs(line.qty)
            )
            line.is_total_cost_computed = True
        return super(PosOrderLine, self - cake_product_lines)._compute_total_cost(stock_moves)
