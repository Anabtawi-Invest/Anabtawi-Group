from odoo import models


class StockReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"

    def _prepare_picking_default_values(self):
        values = super()._prepare_picking_default_values()
        original = self.picking_id
        if original.direct_invoice_id:
            values.update(
                {
                    "direct_invoice_id": original.direct_invoice_id.id,
                    "customer_invoice_id": original.customer_invoice_id.id,
                    "direct_sales_warehouse_id": (
                        original.direct_sales_warehouse_id.id
                    ),
                    "direct_sales_stage": "return",
                }
            )
        return values


class StockReturnPickingLine(models.TransientModel):
    _inherit = "stock.return.picking.line"

    def _prepare_move_default_values(self, new_picking):
        values = super()._prepare_move_default_values(new_picking)
        if self.move_id.direct_invoice_line_id:
            values.update(
                {
                    "direct_invoice_line_id": self.move_id.direct_invoice_line_id.id,
                    "direct_sales_allocation_id": (
                        self.move_id.direct_sales_allocation_id.id
                    ),
                }
            )
        return values
