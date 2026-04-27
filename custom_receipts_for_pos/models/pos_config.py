# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    receipt_design_id = fields.Many2one(
        comodel_name="pos.receipt",
        string="Receipt Design",
        help="Choose the custom POS receipt design used by this Point of Sale.",
    )

    design_receipt = fields.Text(
        related="receipt_design_id.design_receipt",
        string="Receipt XML",
        readonly=True,
    )

    is_custom_receipt = fields.Boolean(
        string="Custom Receipt",
        help="Enable this option to replace the default Odoo POS receipt with the selected custom design.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        for field_name in ["is_custom_receipt", "receipt_design_id", "design_receipt"]:
            if field_name not in fields_to_load:
                fields_to_load.append(field_name)
        return fields_to_load
