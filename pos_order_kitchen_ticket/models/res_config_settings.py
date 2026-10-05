# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_print_order_kitchen_ticket = fields.Boolean(
        related="pos_config_id.print_order_kitchen_ticket", readonly=False
    )
