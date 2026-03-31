from odoo import models
from odoo.tools.float_utils import float_compare


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)

        done_moves = self.filtered(lambda m: m.state == "done" and m.product_id)
        if not done_moves:
            return res

        Discrepancy = self.env["stock.transfer.discrepancy"].sudo()

        for move in done_moves:
            # Only consider "settlement" moves
            if not (move.scrap_id or move.is_inventory or (move.picking_id and move.picking_id.return_id)):
                continue

            truck_loc = False
            # If the move touches a truck location, try to settle against it.
            if move.location_id and move.location_id.is_truck:
                truck_loc = move.location_id
            elif move.location_dest_id and move.location_dest_id.is_truck:
                truck_loc = move.location_dest_id
            if not truck_loc:
                continue

            qty = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id, round=False)
            if float_compare(qty, 0.0, precision_rounding=move.product_id.uom_id.rounding) <= 0:
                continue

            discrepancies = Discrepancy.search(
                [
                    ("truck_location_id", "=", truck_loc.id),
                    ("product_id", "=", move.product_id.id),
                    ("state", "in", ("open", "under_investigation")),
                ],
                order="date asc, id asc",
            )

            remaining = qty
            for disc in discrepancies:
                if float_compare(remaining, 0.0, precision_rounding=move.product_id.uom_id.rounding) <= 0:
                    break
                before = disc.resolved_qty
                disc._apply_resolution(remaining)
                applied = (disc.resolved_qty or 0.0) - (before or 0.0)
                remaining -= applied

        return res
