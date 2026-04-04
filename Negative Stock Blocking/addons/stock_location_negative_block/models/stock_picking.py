from collections import defaultdict

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):

        Quant = self.env["stock.quant"]
        outgoing = defaultdict(float)

        # ---------------------------------------
        # collect outgoing quantities
        # ---------------------------------------
        for picking in self:
            for move in picking.move_ids:

                source = move.location_id

                if not source or source.usage != "internal":
                    continue

                if not source.restrict_negative:
                    continue

                product = move.product_id

                if product.type != "product":
                    continue

                for line in move.move_line_ids:
                    if line.qty_done <= 0:
                        continue

                    qty = line.product_uom_id._compute_quantity(
                        line.qty_done,
                        product.uom_id
                    )

                    key = (product.id, source.id)
                    outgoing[key] += qty

        # ---------------------------------------
        # validate
        # ---------------------------------------
        for (product_id, location_id), out_qty in outgoing.items():

            product = self.env["product.product"].browse(product_id)
            location = self.env["stock.location"].browse(location_id)

            # free available excludes reserved quantities
            free_available = Quant._get_available_quantity(product, location)

            # add back quantities reserved for THIS picking (so first reserved transfer can validate)
            reserved_by_this_picking = 0.0
            for picking in self:
                for move in picking.move_ids:
                    if move.state == "cancel":
                        continue
                    if move.product_id.id != product.id:
                        continue
                    if move.location_id.id != location.id:
                        continue
                    reserved_by_this_picking += float(getattr(move, "reserved_availability", 0.0) or 0.0)

            effective_available = free_available + reserved_by_this_picking

            if float_compare(out_qty, effective_available,
                             precision_rounding=product.uom_id.rounding) > 0:

                raise UserError(_(
                    "Negative stock NOT allowed\n\n"
                    "Location: %s\nProduct: %s\n"
                    "Free Available: %s\nReserved (this transfer): %s\n"
                    "Requested: %s"
                ) % (
                    location.display_name,
                    product.display_name,
                    free_available,
                    reserved_by_this_picking,
                    out_qty,
                ))

        return super().button_validate()
