from odoo import api, fields, models
from odoo.exceptions import UserError

GROUP_XMLID = "branch_product_whitelist.group_branch_restricted_product_selection"
ERROR_MSG = "This product is not allowed for branch internal transfers."


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.model
    def _branch_product_domain(self):
        return self.env["stock.move"]._branch_product_domain()

    product_id = fields.Many2one(
        domain=lambda self: self._branch_product_domain(),
    )

    def _check_branch_product_allowed(self):
        if not self.env.user.has_group(GROUP_XMLID):
            return
        for line in self:
            if line.product_id and not line.product_id.product_tmpl_id.branch_allowed:
                raise UserError(ERROR_MSG)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_branch_product_allowed()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if "product_id" in vals:
            self._check_branch_product_allowed()
        return res
