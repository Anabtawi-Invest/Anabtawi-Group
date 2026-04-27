from odoo import api, fields, models

class PosReceipt(models.Model):
    _name = "pos.receipt"
    _description = "POS Receipts"
    _inherit = ["pos.load.mixin"]

    name = fields.Char()
    design_receipt = fields.Text()

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name", "design_receipt"]
