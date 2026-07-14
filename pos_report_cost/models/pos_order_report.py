from odoo import api, fields, models


class PosOrderReport(models.Model):
    _inherit = 'report.pos.order'

    # Original field is an Integer; redeclared here as a Float with 3 decimals
    # so weighted products (qty < 1) display correctly, e.g. 0.750.
    product_qty = fields.Float(string='Product Quantity', digits=(16, 3), readonly=True)

    standard_price = fields.Float(related='product_id.standard_price', string='Cost')

    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total_cost',
        digits=(16, 3),
    )

    @api.depends('product_qty', 'standard_price')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.product_qty * rec.standard_price
