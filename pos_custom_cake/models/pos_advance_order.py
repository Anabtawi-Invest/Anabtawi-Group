# -*- coding: utf-8 -*-
from odoo import fields, models


class PosAdvanceOrder(models.Model):
    _inherit = "pos.advance.order"

    cake_order_id = fields.Many2one(
        "pos.cake.order",
        string="Custom Cake Order",
        readonly=True,
        copy=False,
        index=True,
        help="When set, this advance was created from Custom Cake and is completed from Cake Orders only.",
    )

    def _create_pos_order(self, session, lines, mark_advance_generated=True):
        order = super()._create_pos_order(
            session, lines, mark_advance_generated=mark_advance_generated
        )
        if self.cake_order_id:
            order.sudo().write({"pos_cake_order_id": self.cake_order_id.id})
        return order

    def action_create_remaining_payment(
        self,
        pos_payment_method_id=None,
        pos_config_id=None,
        amount_tendered=None,
    ):
        result = super().action_create_remaining_payment(
            pos_payment_method_id=pos_payment_method_id,
            pos_config_id=pos_config_id,
            amount_tendered=amount_tendered,
        )
        for order in self:
            if (
                order.cake_order_id
                and order.state == "fully_paid"
                and order.cake_order_id.state != "paid"
            ):
                order.cake_order_id.sudo().action_mark_paid(order.remaining_pos_order_id)
        return result
