from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    demand_qty = fields.Float(
        string="Demand Quantity",
        digits="Product Unit",
        copy=False,
        help="Planned quantity to move for this operation line.",
    )

    def _sync_demand_qty_to_move(self):
        for line in self.filtered("move_id"):
            line_uom = line.product_uom_id or line.move_id.product_uom
            line.move_id.product_uom_qty = line_uom._compute_quantity(
                line.demand_qty,
                line.move_id.product_uom,
                rounding_method="HALF-UP",
            )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.filtered(lambda line: line.demand_qty)._sync_demand_qty_to_move()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if "demand_qty" in vals:
            self._sync_demand_qty_to_move()
        return res

    def read(self, fields=None, load="_classic_read"):
        data = super().read(fields, load)
        if fields and "demand_qty" in fields:
            for line, vals in zip(self, data):
                if not vals.get("demand_qty") and line.quantity and not line.picked:
                    vals["demand_qty"] = line.quantity
        return data

    def _get_fields_stock_barcode(self):
        return super()._get_fields_stock_barcode() + ["demand_qty"]
