# -*- coding: utf-8 -*-

from odoo import fields, models


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

