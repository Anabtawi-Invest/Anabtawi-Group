# -*- coding: utf-8 -*-

from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def action_add_from_catalog(self):
        """Called from the Operations one2many control (model = stock.move)."""
        picking = self.env["stock.picking"].browse(self.env.context.get("order_id"))
        return picking.with_context(
            order_id=picking.id,
            child_field=self.env.context.get("child_field") or "move_ids",
        ).action_add_from_catalog()

