from odoo import models, fields

class StockLocation(models.Model):
    _inherit = 'stock.location'

    restrict_negative = fields.Boolean(
        string='Restrict Negative Stock',
        default=False,
        help='If checked, prevents negative stock in this location.'
    )

