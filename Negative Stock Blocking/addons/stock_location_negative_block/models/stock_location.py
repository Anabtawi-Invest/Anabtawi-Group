from odoo import fields, models

class StockLocation(models.Model):
    _inherit = "stock.location"

    restrict_negative = fields.Boolean(
        string="Restrict Negative Stock",
        help="If enabled, any stock move leaving this location that would make stock negative will be blocked."
    )
