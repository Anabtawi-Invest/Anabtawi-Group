from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    delivery_group_id = fields.Many2one(
        "sale.delivery.group",
        string="Delivery Group",
        index="btree_not_null",
    )

    @api.model
    def _prepare_merge_moves_distinct_fields(self):
        return super()._prepare_merge_moves_distinct_fields() + ["delivery_group_id"]

    def _key_assign_picking(self):
        return super()._key_assign_picking() + (self.delivery_group_id,)

    def _search_picking_for_assignation_domain(self):
        return super()._search_picking_for_assignation_domain() + [
            ("delivery_group_id", "=", self.delivery_group_id.id),
        ]

    def _get_new_picking_values(self):
        vals = super()._get_new_picking_values()
        vals["delivery_group_id"] = self.delivery_group_id[:1].id
        return vals

    def _prepare_procurement_values(self):
        values = super()._prepare_procurement_values()
        values["delivery_group_id"] = self.delivery_group_id
        return values
