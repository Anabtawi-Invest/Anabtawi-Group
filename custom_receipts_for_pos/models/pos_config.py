# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    receipt_design_id = fields.Many2one(
        comodel_name="pos.receipt",
        string="Receipt Design",
        help="Choose any receipt design.",
    )

    design_receipt = fields.Text(
        related="receipt_design_id.design_receipt",
        string="Receipt XML",
        readonly=True,
    )

    is_custom_receipt = fields.Boolean(
        string="Is Custom Receipt",
        help="Enable this option to use a custom POS receipt design.",
    )

    def _load_pos_data_read(self, records, config):
        """
        Odoo 19 POS loads pos.config with an empty fields list from the core loader.
        Empty fields means Odoo keeps the normal POS config payload.

        Do not override _load_pos_data_fields for pos.config here,
        because returning only custom fields removes important fields such as:
        currency_id, company_id, payment_method_ids, pricelist_id, etc.
        That is what caused:
        Cannot read properties of undefined reading currency_id

        This method safely injects only our custom values after Odoo loads
        the original POS config data.
        """
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
