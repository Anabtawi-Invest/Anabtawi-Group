# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        """
        Block negative stock ONLY for Internal Transfers.
        Do NOT interfere with procurement, MRP, purchases, receipts, or deliveries.
        """

        # 🔹 Apply ONLY to Internal Transfers
        internal_pickings = self.filtered(
            lambda p: p.picking_type_id and p.picking_type_id.code == "internal"
        )

        # If none are internal, behave exactly like standard Odoo
        if not internal_pickings:
            return super().button_validate()

        Quant = self.env["stock.quant"]
        outgoing = defaultdict(float)

        # 🔹 Collect quantities actually being moved (qty_done)
        for picking in internal_pickings:
            for move in picking.move_ids:
                product = move.product_id

                # Only stockable products
                if product.type != "product":
                    continue

                source_location = move.location_id

                # Only internal source locations
                if not source_location or source_location.usage != "internal":
                    continue

                for line in move.move_line_ids:
                    if line.qty_done <= 0:
                        continue

                    qty = line.product_uom_id._compute_quantity(
                        line.qty_done,
                        product.uom_id
                    )

                    outgoing[(product.id, source_location.id)] += qty

        # 🔹 Validate availability (AFTER reservation)
        for (product_id, location_id), out_qty in outgoing.items():
            product = self.env["product.product"].browse(product_id)
            location = self.env["stock.location"].browse(location_id)

            available_qty = Quant._get_available_quantity(product, location)

            if float_compare(
                out_qty,
                available_qty,
                precision_rounding=product.uom_id.rounding
            ) > 0:
                raise UserError(_(
                    "Negative stock is NOT allowed for Internal Transfers.\n\n"
                    "Location: %(location)s\n"
                    "Product: %(product)s\n"
                    "Available: %(available)s\n"
                    "Requested: %(requested)s"
                ) % {
                    "location": location.display_name,
                    "product": product.display_name,
                    "available": available_qty,
                    "requested": out_qty,
                })

        return super().button_validate()
