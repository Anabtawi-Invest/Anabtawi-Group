from odoo import models
from odoo.fields import Domain
from odoo.exceptions import UserError


GROUP_XMLID = "branch_product_whitelist.group_branch_restricted_product_selection"
ERROR_MSG = "This product is not allowed for branch internal transfers."


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _is_branch_internal_transfer(self):
        """Apply the whitelist only to real internal transfer pickings.

        This prevents POS/outgoing sales, Talabat payments, deliveries, receipts,
        and other stock flows from being blocked by the branch transfer rule.
        """
        self.ensure_one()
        return bool(self.picking_type_id and self.picking_type_id.code == "internal")

    def _get_product_catalog_domain(self):
        domain = super()._get_product_catalog_domain()

        if (
            len(self) == 1
            and self._is_branch_internal_transfer()
            and self.env.user.has_group(GROUP_XMLID)
        ):
            domain &= Domain("product_tmpl_id.branch_allowed", "=", True)

        return domain

    def _update_order_line_info(self, product_id, quantity, *, child_field="move_ids", **kwargs):
        if (
            self._is_branch_internal_transfer()
            and self.env.user.has_group(GROUP_XMLID)
        ):
            product = self.env["product.product"].browse(product_id)
            if product and not product.product_tmpl_id.branch_allowed:
                raise UserError(ERROR_MSG)

        return super()._update_order_line_info(
            product_id,
            quantity,
            child_field=child_field,
            **kwargs
        )
