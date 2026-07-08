from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    barcode_show_demand_qty = fields.Boolean(
        string="Show Demand Quantity in Barcode",
        help="If enabled, the barcode product form shows the demand quantity field.",
    )

    def _get_barcode_config(self):
        config = super()._get_barcode_config()
        config["barcode_show_demand_qty"] = self.barcode_show_demand_qty
        return config
