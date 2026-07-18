# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    apply_routes_on_confirm = fields.Boolean(
        string="Apply Routes on Confirm",
        default=True,
        help="When confirming an internal transfer of this type, apply product "
             "pull routes so rules with 'Trigger Another Rule' create upstream "
             "transfers automatically.",
    )
