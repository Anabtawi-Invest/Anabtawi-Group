from odoo import fields, models


class PosOrderReport(models.Model):
    _inherit = 'report.pos.order'

    standard_price = fields.Float(related='product_id.standard_price', string='Cost')
