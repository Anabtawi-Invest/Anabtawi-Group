# -*- coding: utf-8 -*-

from odoo import fields, models,api


class PosOrder(models.Model):
    _inherit = "pos.order"

    is_advance_generated = fields.Boolean(
        string="Advance Generated",
        default=False,
        help="Technical flag used to exclude this order from POS session closing accounting (advance module flow).",
    )
    advance_order_id = fields.Many2one(
        "pos.advance.order",
        string="Advance Order",
        readonly=True,
        copy=False,
        index=True,
    )

    advance_pledge_line_ids = fields.One2many(
        "pos.advance.order.pledge",
        "pos_order_id",
        string="Pledge Lines",
        readonly=True,
        copy=False,
    )


    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)

        for order in orders:
            if order.is_refund and order.refunded_order_id:
                original_order = order.refunded_order_id

                if original_order.advance_order_id:
                    advance = original_order.advance_order_id
                    if advance.state != "cancel":
                        advance.write({"state": "cancel"})

        return orders
