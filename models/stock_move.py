from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.model
    def _branch_product_domain(self):
        if self.env.user.has_group("branch_product_whitelist.group_branch_restricted_product_selection"):
            return [("product_tmpl_id.branch_allowed", "=", True)]
        return []

    product_id = fields.Many2one(
        "product.product",
        domain=lambda self: self._branch_product_domain(),
    )
