from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = "product.template"

    x_net_weight_kg = fields.Float(string="Net Weight (Kg)", digits="Stock Weight")
    x_gross_weight_kg = fields.Float(string="Gross Weight (Kg)", digits="Stock Weight")
    x_package_type_id = fields.Many2one("packing.package.type", string="Package Type")
    x_qty_per_carton = fields.Integer(string="Qty per Carton", default=0)
