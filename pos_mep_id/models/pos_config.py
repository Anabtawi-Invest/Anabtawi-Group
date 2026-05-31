# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    mep_payment_method_ids = fields.Many2many(
        "pos.payment.method",
        "pos_config_mep_payment_method_rel",
        "config_id",
        "payment_method_id",
        string="MEPs Payment Methods",
        help="When one of these payment methods is selected in POS, cashier must enter a MEP ID.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        # Core pos.config currently returns [] meaning "load all fields".
        if not fields_to_load:
            return fields_to_load
        if "mep_payment_method_ids" not in fields_to_load:
            fields_to_load.append("mep_payment_method_ids")
        return fields_to_load
