from odoo import models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _apply_inventory(self, date=None):
        # Capture resolutions before applying because calling super clears inventory fields.
        resolutions = []
        for quant in self:
            if not (quant.location_id and quant.location_id.is_truck and quant.product_id):
                continue

            diff = quant.inventory_diff_quantity
            if not diff:
                continue

            qty_prod_uom = quant.product_uom_id._compute_quantity(
                abs(diff),
                quant.product_id.uom_id,
                round=False,
            )

            resolutions.append((quant.location_id, quant.product_id, qty_prod_uom))

        # ✅ FIX: pass argument positionally (not keyword)
        res = super()._apply_inventory(date)

        Discrepancy = self.env["stock.transfer.discrepancy"]
        truck_locations_to_recompute = set()

        for truck_loc, product, qty in resolutions:
            Discrepancy.apply_resolution(truck_loc, product, qty)
            truck_locations_to_recompute.add(truck_loc)

        # Trigger recompute of has_open_discrepancy on affected truck locations
        if truck_locations_to_recompute:
            self.env["stock.location"].browse(
                [loc.id for loc in truck_locations_to_recompute]
            )._compute_has_open_discrepancy()

        return res
