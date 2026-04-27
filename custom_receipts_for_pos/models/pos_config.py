# -*- coding: utf-8 -*-
from odoo import fields, models


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
        help="Enable this option to use the selected custom POS receipt design.",
    )

    def _load_pos_data_read(self, records, config):
        result = super()._load_pos_data_read(records, config)

        for config_data in result:
            current_config = self.browse(config_data.get("id")).exists()

            if not current_config:
                config_data.update({
                    "is_custom_receipt": False,
                    "receipt_design_id": False,
                    "design_receipt": False,
                })
                continue

            config_data.update({
                "is_custom_receipt": bool(current_config.is_custom_receipt),
                "receipt_design_id": current_config.receipt_design_id.id or False,
                "design_receipt": current_config.design_receipt or False,
            })

        return result
