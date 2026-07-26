# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    pos_cake_order_id = fields.Many2one(
        "pos.cake.order",
        string="Custom Cake Order",
        readonly=True,
        copy=False,
    )

    def action_pos_order_paid(self):
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
