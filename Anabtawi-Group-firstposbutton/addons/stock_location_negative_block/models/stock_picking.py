from collections import defaultdict

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):

        Quant = self.env["stock.quant"]
        outgoing = defaultdict(float)
        raise UserError("Negative Stock Is Not Allowed, Be Carefull My Friend")

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

            available = Quant._get_available_quantity(product, location)

            if float_compare(out_qty, available,
                             precision_rounding=product.uom_id.rounding) > 0:

                raise UserError(_(
                    "Negative stock NOT allowed\n\n"
                    "Location: %s\nProduct: %s\nAvailable: %s\nRequested: %s"
                ) % (
                    location.display_name,
                    product.display_name,
                    available,
                    out_qty,
                ))

        return super().button_validate()
