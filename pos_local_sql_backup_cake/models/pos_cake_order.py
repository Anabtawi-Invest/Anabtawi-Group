# -*- coding: utf-8 -*-

from odoo import fields, models


class PosCakeOrder(models.Model):
    _inherit = "pos.cake.order"

    local_uuid = fields.Char(
        string="Local UUID",
        index=True,
        copy=False,
        help="Stable id from the cashier POS used to sync an offline create only once.",
    )

    _sql_constraints = [
        (
            "pos_cake_order_local_uuid_uniq",
            "unique(local_uuid)",
            "This local cake was already created in Odoo.",
        ),
    ]
