from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    demand_qty = fields.Float(
        string="الكمية المطلوبة من المصنع",
        digits="Product Unit",
        copy=False,
        help="Planned quantity to move for this operation line.",
    )
    show_barcode_demand_qty = fields.Boolean(
        related="picking_type_id.barcode_show_demand_qty",
    )

    def _sync_demand_qty_to_move(self):
        lines = self.filtered(
            lambda line: line.move_id and line.picking_type_id.barcode_show_demand_qty
        )
        for line in lines:
            line_uom = line.product_uom_id or line.move_id.product_uom
            line.move_id.product_uom_qty = line_uom._compute_quantity(
                line.demand_qty,
                line.move_id.product_uom,
                rounding_method="HALF-UP",
            )

    def _picking_type_from_vals(self, vals):
        picking = (
            self.env["stock.picking"].browse(vals["picking_id"])
            if vals.get("picking_id")
            else self.env["stock.picking"]
        )
        move = (
            self.env["stock.move"].browse(vals["move_id"])
            if vals.get("move_id")
            else self.env["stock.move"]
        )
        if picking:
            return picking.picking_type_id
        if move:
            return move.picking_type_id
        return self.env["stock.picking.type"]

    def _scanned_qty_without_demand(self, vals):
        """Done quantity on a new barcode line that was not stored as demand.

        Reservation creates a line with a quantity and picked=False. A product
        scan creates a line with qty_done, or with quantity and picked=True.
        """
        if vals.get("demand_qty"):
            return 0.0
        if vals.get("qty_done"):
            return vals["qty_done"]
        if vals.get("picked") and vals.get("quantity"):
            return vals["quantity"]
        return 0.0

    def _prepare_demand_mode_vals(self, vals):
        picking_type = self._picking_type_from_vals(vals)
        if not picking_type or not picking_type.barcode_show_demand_qty:
            return
        demand_qty = vals.get("demand_qty") or self._scanned_qty_without_demand(vals)
        if not demand_qty:
            return
        vals["demand_qty"] = demand_qty
        vals.pop("qty_done", None)
        vals["quantity"] = 0
        vals["picked"] = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._prepare_demand_mode_vals(vals)
        lines = super().create(vals_list)
        lines.filtered(lambda line: line.demand_qty)._sync_demand_qty_to_move()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if "demand_qty" in vals:
            self._sync_demand_qty_to_move()
            stray_done = self.filtered(
                lambda line: line.show_barcode_demand_qty
                and line.demand_qty
                and not line.picked
                and line.quantity
            )
            if stray_done:
                stray_done.with_context(preserve_state=True).write(
                    {"quantity": 0, "picked": False}
                )
        return res

    def read(self, fields=None, load="_classic_read"):
        data = super().read(fields, load)
        if fields and "demand_qty" in fields:
            for line, vals in zip(self, data):
                if not vals.get("demand_qty") and line.quantity and not line.picked:
                    vals["demand_qty"] = line.quantity
        return data

    def _get_fields_stock_barcode(self):
        return super()._get_fields_stock_barcode() + [
            "demand_qty",
            "show_barcode_demand_qty",
        ]
