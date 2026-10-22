from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _force_quantity_from_demand(self):
        """For chained (next) transfers, set Done qty = Demand when stock is missing.

        Standard Odoo leaves quantity at 0 if reservation fails. Business wants
        the next transfer to still show Demand as the default Done quantity.
        """
        moves = self.filtered(
            lambda m: m.move_orig_ids
            and m.state not in ("draft", "done", "cancel")
            and not m.picked
            and m.product_uom_qty
            and m.uom_id.compare(m.quantity, m.product_uom_qty) < 0
        )
        for move in moves:
            move.quantity = move.product_uom_qty

    def _action_confirm(self, merge=True, merge_into=False, create_proc=True):
        moves = super()._action_confirm(
            merge=merge, merge_into=merge_into, create_proc=create_proc
        )
        moves._force_quantity_from_demand()
        return moves

    def _action_assign(self, force_qty=False):
        res = super()._action_assign(force_qty=force_qty)
        self._force_quantity_from_demand()
        return res
