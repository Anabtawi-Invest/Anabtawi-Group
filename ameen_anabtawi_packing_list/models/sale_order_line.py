from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x_qty_per_carton = fields.Integer(string="Qty per Carton", default=0)

    @api.onchange("product_id")
    def _onchange_product_id_set_qty_per_carton(self):
        for line in self:
            if line.product_id:
                line.x_qty_per_carton = line.product_id.product_tmpl_id.x_qty_per_carton or 0
