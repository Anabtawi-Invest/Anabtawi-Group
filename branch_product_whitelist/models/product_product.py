from odoo import api, models

from .stock_move_line import GROUP_XMLID


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _get_branch_whitelist_extra_domain(self):
        if not self.env.user.has_group(GROUP_XMLID):
            return []

        ctx = self.env.context
        picking = self.env["stock.picking"]

        picking_id = ctx.get("default_picking_id")
        if not picking_id and ctx.get("active_model") == "stock.picking":
            picking_id = ctx.get("active_id")

        if picking_id:
            picking = self.env["stock.picking"].browse(picking_id)
            if picking.exists() and picking.picking_type_id.code == "internal":
                return [("product_tmpl_id.branch_allowed", "=", True)]
            return []

        picking_type_id = ctx.get("default_picking_type_id")
        if picking_type_id:
            picking_type = self.env["stock.picking.type"].browse(picking_type_id)
            if picking_type.exists() and picking_type.code == "internal":
                return [("product_tmpl_id.branch_allowed", "=", True)]

        return []

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        args = list(args or []) + self._get_branch_whitelist_extra_domain()
        return super().name_search(name, args, operator, limit)
