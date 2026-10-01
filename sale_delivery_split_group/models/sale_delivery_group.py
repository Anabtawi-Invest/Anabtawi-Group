from odoo import fields, models


class SaleDeliveryGroup(models.Model):
    _name = "sale.delivery.group"
    _description = "Sale Delivery Group"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
