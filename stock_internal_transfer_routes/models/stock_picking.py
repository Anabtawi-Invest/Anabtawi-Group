# -*- coding: utf-8 -*-
from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def action_confirm(self):
        self._apply_routes_before_confirm()
        return super().action_confirm()

    def _apply_routes_before_confirm(self):
        """Apply pull routes on draft moves of eligible internal transfers."""
        pickings = self.filtered(
            lambda p: p.picking_type_id.code == "internal"
            and p.picking_type_id.apply_routes_on_confirm
        )
        draft_moves = pickings.move_ids.filtered(lambda m: m.state == "draft")
        to_adjust = draft_moves.filtered(
            lambda m: m.product_id.route_ids or m.product_id.categ_id.total_route_ids
        )
        if to_adjust:
            to_adjust._adjust_procure_method()
