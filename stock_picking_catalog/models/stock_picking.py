# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import models
from odoo.fields import Domain


class StockPicking(models.Model):
    _inherit = ["stock.picking", "product.catalog.mixin"]

    def _default_order_line_values(self, child_field=False):
        default_data = super()._default_order_line_values(child_field)
        new_default_data = self.env["stock.move"]._get_product_catalog_lines_data(parent_record=self)
        return {**default_data, **new_default_data}

    def _get_product_catalog_domain(self) -> Domain:
        # Keep same product domain logic used by stock moves in pickings (goods).
        return super()._get_product_catalog_domain() & Domain("type", "=", "consu")

    def _get_product_catalog_order_data(self, products, **kwargs):
        res = super()._get_product_catalog_order_data(products, **kwargs)
        for product in products:
            res[product.id] |= self._get_product_price_and_data(product)
        return res

    def _get_product_price_and_data(self, product):
        """The catalog UI expects a `price` field; picking doesn't use prices, but list_price works."""
        self.ensure_one()
        return {"price": product.list_price, "uomDisplayName": product.uom_id.display_name}

    def _get_product_catalog_record_lines(self, product_ids, **kwargs):
        self.ensure_one()
        grouped = defaultdict(lambda: self.env["stock.move"])
        for move in self.move_ids:
            if move.product_id.id in product_ids:
                grouped[move.product_id] |= move
        return grouped

    def _is_readonly(self):
        self.ensure_one()
        return self.state == "cancel" or (self.state == "done" and self.is_locked)

    def _update_order_line_info(self, product_id, quantity, *, child_field="move_ids", **kwargs):
        """Update or create stock moves from the product catalog for this picking."""
        self.ensure_one()

        moves = self[child_field].filtered(lambda m: m.product_id.id == product_id)
        if moves:
            # If multiple lines exist for same product, catalog will mark as readOnly (see stock.move).
            move = moves[:1]
            if quantity != 0:
                move.product_uom_qty = quantity
            else:
                if self.state == "draft":
                    moves.unlink()
                else:
                    move.product_uom_qty = 0
        elif quantity > 0:
            self.env["stock.move"].create(
                {
                    "picking_id": self.id,
                    "product_id": product_id,
                    "product_uom_qty": quantity,
                    "location_id": self.location_id.id,
                    "location_dest_id": self.location_dest_id.id,
                }
            )

        return self.env["product.product"].browse(product_id).list_price

