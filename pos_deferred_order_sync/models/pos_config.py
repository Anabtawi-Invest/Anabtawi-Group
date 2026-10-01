# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    deferred_order_sync = fields.Boolean(
        string="Hold Orders Until Closing",
        help="Paid orders are kept on the device and sent to the server when the register "
        "is closed, even while online. Refunds, invoiced, "
        "cake, pledge and scheduled orders are still sent immediately.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        # Empty list means "load all fields".
        if fields_to_load and "deferred_order_sync" not in fields_to_load:
            fields_to_load.append("deferred_order_sync")
        return fields_to_load
