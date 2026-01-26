from odoo import fields, models

class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    is_gift = fields.Boolean(string="Gift", default=False)
    gift_original_price_unit = fields.Float(string="Gift Original Unit Price", default=0.0)
