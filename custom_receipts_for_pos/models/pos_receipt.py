# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosReceipt(models.Model):
    _name = "pos.receipt"
    _description = "POS Receipts"
    _inherit = ["pos.load.mixin"]  # ✅ IMPORTANT for Odoo 19 POS loading

    name = fields.Char(string="Name", help="Name of the pos receipt")
    design_receipt = fields.Text(string="Receipt XML", help="Add your customised receipts for pos")

    @api.model
    def _load_pos_data_domain(self, data, config):
        """Load all receipt designs to POS."""
        return []

    @api.model
    def _load_pos_data_fields(self, config):
        """Fields to be read and sent to POS UI."""
        return ["id", "name", "design_receipt"]
