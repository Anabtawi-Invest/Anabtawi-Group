from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    available_for_direct_ordering = fields.Boolean(string='Available for Direct Ordering')
    direct_ordering_name = fields.Char(string='Ordering Display Name')
    direct_ordering_description = fields.Text(string='Ordering Description')
    direct_ordering_preparation_minutes = fields.Integer(string='Preparation Minutes', default=15)
    direct_ordering_category = fields.Char(string='Ordering Category')
    aggregator_sku = fields.Char(string='Aggregator SKU')
    talabat_item_id = fields.Char(string='Talabat Item ID')
    careem_item_id = fields.Char(string='Careem Item ID')
