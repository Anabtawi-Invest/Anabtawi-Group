# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosReceipt(models.Model):
    _name = "pos.receipt"
    _description = "POS Receipts"

    name = fields.Char(string="Name", help="Name of the pos receipt")
    design_receipt = fields.Text(string="Receipt XML", help="Add your customised receipts for pos")

    @api.model
    def _load_pos_data(self, data, config):
        """
        Odoo 19 POS expects each loaded model to provide a loader method that returns
        JSON-serializable data (usually list of dicts).
        We explicitly implement it to avoid relying on mixins/signatures.
        """
        receipts = self.search([])  # load all designs
        return receipts.read(["id", "name", "design_receipt"])
