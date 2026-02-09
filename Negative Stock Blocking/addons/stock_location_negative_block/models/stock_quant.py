from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # ======================================================
    # SAFE UNIVERSAL PROTECTION (works for ALL call styles)
    # ======================================================
    def _update_available_quantity(self, *args, **kwargs):

        product = args[0]
        location = args[1]

        # quantity may come from different names
        quantity = (
            kwargs.get("quantity")
            or kwargs.get("reserved_quantity")
            or (args[2] if len(args) > 2 else 0)
        )

        # only outgoing
        if quantity and quantity < 0:

            if location.usage == "internal" and location.restrict_negative:

                available = self._get_available_quantity(product, location)
                requested = abs(quantity)

                if float_compare(
                    requested,
                    available,
                    precision_rounding=product.uom_id.rounding
                ) > 0:

                    raise UserError(_(
                        "❌ Negative stock NOT allowed\n\n"
                        "Location: %s\nProduct: %s\nAvailable: %s\nRequested: %s"
                    ) % (
                        location.display_name,
                        product.display_name,
                        available,
                        requested,
                    ))

        return super()._update_available_quantity(*args, **kwargs)
