# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _adjust_procure_method(self, picking_type_code=False):
        """Match pull rules using destination parent locations as well.

        Standard Odoo only walks up the *source* location tree and requires an
        exact destination match. For internal resupply routes, demand is often
        created on a child location (e.g. a branch bin) while the rule targets
        the warehouse stock location.
        """
        if not self.env.context.get("internal_transfer_apply_routes"):
            return super()._adjust_procure_method(picking_type_code=picking_type_code)

        for move in self:
            product_id = move.product_id
            rule = self.env["stock.rule"]
            location = move.location_id
            while location and not rule:
                domain = [
                    ("location_src_id", "=", location.id),
                    ("location_dest_id", "parent_of", move.location_dest_id.id),
                    ("action", "!=", "push"),
                ]
                if picking_type_code:
                    domain.append(("picking_type_id.code", "=", picking_type_code))
                rule = self.env["stock.rule"]._search_rule(
                    False,
                    move.packaging_uom_id,
                    product_id,
                    move.warehouse_id or move.picking_type_id.warehouse_id,
                    domain,
                )
                if rule:
                    break
                location = location.location_id
            if not rule:
                move.procure_method = "make_to_stock"
                continue
            move.rule_id = rule.id
            if rule.procure_method in ("make_to_stock", "make_to_order"):
                move.procure_method = rule.procure_method
            else:
                move.procure_method = "make_to_stock"
