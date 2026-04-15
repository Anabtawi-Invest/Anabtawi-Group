from odoo import models
from odoo.fields import Domain
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_product_catalog_domain(self):
        domain = super()._get_product_catalog_domain()

        if self.env.user.has_group("branch_product_whitelist.group_branch_restricted_product_selection"):
            domain &= Domain("product_tmpl_id.branch_allowed", "=", True)

        return domain

    def _update_order_line_info(self, product_id, quantity, *, child_field="move_ids", **kwargs):
        if self.env.user.has_group("branch_product_whitelist.group_branch_restricted_product_selection"):
            product = self.env["product.product"].browse(product_id)
            if not product.product_tmpl_id.branch_allowed:
                raise UserError("This product is not allowed for branch internal transfers.")

        return super()._update_order_line_info(
            product_id,
            quantity,
            child_field=child_field,
            **kwargs
        )
