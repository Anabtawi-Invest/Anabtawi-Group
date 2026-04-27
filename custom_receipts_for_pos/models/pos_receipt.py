# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosReceipt(models.Model):
    _name = "pos.receipt"
    _description = "POS Receipt Design"
    _inherit = "pos.load.mixin"

    name = fields.Char(
        string="Name",
        required=True,
        help="Name of the POS receipt design.",
    )

    design_receipt = fields.Text(
        string="Receipt XML",
        required=True,
        help="Custom OWL/QWeb receipt template used in the POS frontend.",
    )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            "id",
            "name",
            "design_receipt",
        ]
