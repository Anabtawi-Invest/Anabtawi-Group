from odoo import api, fields, models


GROUP_XMLID = "branch_product_whitelist.group_branch_restricted_product_selection"


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.model
    def _is_internal_transfer_context(self):
        """Return True only when the current context clearly belongs to an internal transfer.

        Do not globally restrict stock.move products because POS sales also create
        stock moves. The UI/domain restriction should only appear for internal
        transfer forms/catalog usage.
        """
        ctx = self.env.context
        picking_id = ctx.get("default_picking_id") or ctx.get("active_id") if ctx.get("active_model") == "stock.picking" else ctx.get("default_picking_id")
        if picking_id:
            picking = self.env["stock.picking"].browse(picking_id)
            return bool(picking.exists() and picking.picking_type_id.code == "internal")

        picking_type_id = ctx.get("default_picking_type_id")
        if picking_type_id:
            picking_type = self.env["stock.picking.type"].browse(picking_type_id)
            return bool(picking_type.exists() and picking_type.code == "internal")

        return False

    @api.model
    def _branch_product_domain(self):
        if (
            self.env.user.has_group(GROUP_XMLID)
            and self._is_internal_transfer_context()
        ):
            return [("product_tmpl_id.branch_allowed", "=", True)]
        return []

    product_id = fields.Many2one(
        "product.product",
        domain=lambda self: self._branch_product_domain(),
    )
