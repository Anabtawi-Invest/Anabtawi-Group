from odoo import models


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    def do_scrap(self):
        res = super().do_scrap()
        Discrepancy = self.env["stock.transfer.discrepancy"]
        for scrap in self:
            if scrap.state != "done":
                continue
            if not scrap.location_id.is_truck:
                continue
            qty_prod_uom = scrap.product_uom_id._compute_quantity(
                scrap.scrap_qty, scrap.product_id.uom_id, round=False
            )
            # Scrap from truck location resolves BOTH dispatch and receipt discrepancies
            # (stage=None means resolve all stages)
            Discrepancy.apply_resolution(
                scrap.location_id, scrap.product_id, qty_prod_uom, stage=None
            )
        return res

