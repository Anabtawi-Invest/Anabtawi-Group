from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _force_quantity_from_demand(self):
        """For chained (next) transfers, set Done qty = Demand when stock is missing.

        Standard Odoo leaves quantity at 0 if reservation fails. Business wants
        the next transfer to still show Demand as the default Done quantity.
        """
        def _need_force(m):
            if not (
                m.move_orig_ids
                and m.state not in ("draft", "done", "cancel")
                and not m.picked
                and m.product_uom_qty
            ):
                return False
            # Odoo 19 core renamed product_uom -> uom_id; staging still has product_uom
            uom = m.product_uom if "product_uom" in m._fields else m.uom_id
            return uom.compare(m.quantity, m.product_uom_qty) < 0

        moves = self.filtered(_need_force)
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
