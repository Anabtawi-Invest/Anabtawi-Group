from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_picking_operations_report_moves(self):
        """Moves printed on Picking Operations.

        Standard Odoo only prints moves with done quantity > 0.
        Also include non-cancelled moves that still have demand > 0
        so receivers can see expected products before qty is entered.
        """
        self.ensure_one()

        def _include(move):
            if move.state == "cancel" or not move.product_uom_qty:
                return False
            lines = move.move_line_ids.filtered(lambda ml: not ml.is_entire_pack)
            if lines:
                return True
            # Demand exists but no detailed lines / done still 0
            return not move.move_line_ids

        moves = self.move_ids.filtered(_include)
        return moves.sorted(
            key=lambda move: (
                (
                    move.move_line_ids[0].location_id.complete_name
                    if move.move_line_ids
                    else move.location_id.complete_name
                )
                or "",
                (
                    move.move_line_ids[0].location_dest_id.complete_name
                    if move.move_line_ids
                    else move.location_dest_id.complete_name
                )
                or "",
                move.product_id.display_name or "",
            )
        )
