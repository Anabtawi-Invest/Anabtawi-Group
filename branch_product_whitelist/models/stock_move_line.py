from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

GROUP_XMLID = "branch_product_whitelist.group_branch_restricted_product_selection"
ERROR_MSG = "This product is not allowed for branch internal transfers."


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    branch_product_id_domain = fields.Binary(compute="_compute_branch_product_id_domain")

    @api.model
    def _branch_product_domain(self):
        return self.env["stock.move"]._branch_product_domain()

    product_id = fields.Many2one(
        domain=lambda self: self._branch_product_domain(),
    )

    def _is_branch_internal_transfer_line(self):
        self.ensure_one()
        picking = self.picking_id or self.move_id.picking_id
        return bool(picking and picking.picking_type_id.code == "internal")

    @api.depends("company_id", "picking_id", "move_id.picking_id", "picking_id.picking_type_id", "move_id.picking_id.picking_type_id")
    def _compute_branch_product_id_domain(self):
        for line in self:
            domain = Domain([
                ("type", "=", "consu"),
                "|",
                ("company_id", "=", False),
                ("company_id", "parent_of", line.company_id.id or line.env.company.id),
            ])
            if (
                line.env.user.has_group(GROUP_XMLID)
                and line._is_branch_internal_transfer_line()
            ):
                domain &= Domain("product_tmpl_id.branch_allowed", "=", True)
            line.branch_product_id_domain = domain

    def _check_branch_product_allowed(self):
        if not self.env.user.has_group(GROUP_XMLID):
            return
        for line in self:
            if (
                line._is_branch_internal_transfer_line()
                and line.product_id
                and not line.product_id.product_tmpl_id.branch_allowed
            ):
                raise UserError(ERROR_MSG)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_branch_product_allowed()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if "product_id" in vals or "picking_id" in vals or "move_id" in vals:
            self._check_branch_product_allowed()
        return res
