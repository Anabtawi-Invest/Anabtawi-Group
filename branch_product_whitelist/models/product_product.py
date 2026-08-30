from odoo import api, models

from .stock_move_line import GROUP_XMLID


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _get_branch_whitelist_extra_domain(self):
        if not self.env.user.has_group(GROUP_XMLID):
            return []
        ctx = self.env.context
        if ctx.get("default_picking_id") or ctx.get("active_model") == "stock.move.line":
            return [("product_tmpl_id.branch_allowed", "=", True)]
        return []

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100):
        domain = list(domain or []) + self._get_branch_whitelist_extra_domain()
        return super().name_search(name, domain=domain, operator=operator, limit=limit)
