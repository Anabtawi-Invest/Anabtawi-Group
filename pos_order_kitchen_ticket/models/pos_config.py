# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    print_order_kitchen_ticket = fields.Boolean(
        string="Print Order Ticket After Receipt",
        help="After the first customer receipt of a paid order, print a second ticket "
        "with the order number and products (no prices) on the same printer.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        # Empty list means "load all fields".
        if fields_to_load and "print_order_kitchen_ticket" not in fields_to_load:
            fields_to_load.append("print_order_kitchen_ticket")
        return fields_to_load
