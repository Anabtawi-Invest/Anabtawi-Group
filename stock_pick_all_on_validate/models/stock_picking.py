from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _move_uom(self, move):
        return move.product_uom if "product_uom" in move._fields else move.uom_id

    def _pick_all_open_lines(self):
        """Set Picked on every open move and move line.

        Lines are written directly. If the move is already picked, writing
        the move again does not update a line that is still false, and
        validation would delete that line and drop its quantity to 0.
        """
        pickings = self.filtered(
            lambda picking: picking.state not in ("done", "cancel")
            and picking.picking_type_id.pick_all_on_validate
        )
        moves = pickings.move_ids.filtered(lambda move: move.state not in ("done", "cancel"))
        lines = moves.move_line_ids.filtered(
            lambda line: line.state not in ("done", "cancel")
        )
        if lines:
            lines.picked = True
        if moves:
            moves.picked = True

    def button_validate(self):
        flagged = self.filtered(
            lambda picking: picking.state not in ("done", "cancel")
            and picking.picking_type_id.pick_all_on_validate
        )
        drafts = flagged.filtered(lambda picking: picking.state == "draft")
        if drafts:
            # Reserve while Picked is still false. Then fill an empty done
            # quantity from demand, which is what core Validate does for a draft.
            drafts.action_confirm()
            for move in drafts.move_ids:
                uom = self._move_uom(move)
                if uom.is_zero(move.quantity) and not uom.is_zero(move.product_uom_qty):
                    move.quantity = move.product_uom_qty
        flagged._pick_all_open_lines()
        return super().button_validate()

    def _pre_action_done_hook(self):
        # Runs after a draft transfer has been confirmed, and before the
        # backorder check and the done path.
        self._pick_all_open_lines()
        return super()._pre_action_done_hook()
