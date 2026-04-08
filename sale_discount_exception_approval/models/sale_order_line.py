# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools import float_compare


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    allowed_discount_limit = fields.Float(
        string="Allowed Discount Max (%)",
        compute="_compute_allowed_discount_limit",
        store=True,
        readonly=True,
        help="Maximum allowed discount percentage (ceiling) based on quantity tier.",
    )

    discount_exceeds_limit = fields.Boolean(
        string="Discount Exceeds Limit",
        compute="_compute_discount_exceeds_limit",
        store=True,
        readonly=True,
        help="True if Discount (%) is higher than the allowed ceiling for its quantity tier.",
    )

    discount_gt_5 = fields.Boolean(
        string="Discount > 5%",
        compute="_compute_discount_gt_5",
        store=True,
        readonly=True,
        help="True if Discount (%) is greater than 5%. Used for dual approval requirement.",
    )

    def _get_allowed_discount_limit(self):
        """Tier ceiling (range-based rule, not fixed): <100=0, 100-<200=5, >=200=10."""
        self.ensure_one()
        qty = self.product_uom_qty or 0.0
        if qty < 100:
            return 0.0
        if qty < 200:
            return 5.0
        return 10.0

    @api.depends("product_uom_qty", "display_type")
    def _compute_allowed_discount_limit(self):
        for line in self:
            if line.display_type:
                line.allowed_discount_limit = 0.0
            else:
                line.allowed_discount_limit = line._get_allowed_discount_limit()

    @api.depends("discount", "allowed_discount_limit", "display_type")
    def _compute_discount_exceeds_limit(self):
        precision = self.env["decimal.precision"].precision_get("Discount") or 2
        for line in self:
            if line.display_type:
                line.discount_exceeds_limit = False
                continue
            line_discount = line.discount or 0.0
            limit = line.allowed_discount_limit or 0.0
            line.discount_exceeds_limit = float_compare(
                line_discount, limit, precision_digits=precision
            ) > 0

    @api.depends("discount", "display_type")
    def _compute_discount_gt_5(self):
        precision = self.env["decimal.precision"].precision_get("Discount") or 2
        for line in self:
            if line.display_type:
                line.discount_gt_5 = False
                continue
            line.discount_gt_5 = float_compare(line.discount or 0.0, 5.0, precision_digits=precision) > 0

    # ---- Reset approvals if something relevant changes ----
    def _notify_parent_lines_changed(self, chatter_reason=None):
        orders = self.mapped("order_id")
        if orders:
            orders._on_discount_relevant_change(chatter_reason=chatter_reason)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._notify_parent_lines_changed(chatter_reason="Order lines changed (added). Discount approvals reset if needed.")
        return lines

    def write(self, vals):
        relevant = {"product_uom_qty", "discount", "display_type", "product_uom_id"}
        must_notify = bool(relevant.intersection(vals.keys()))
        res = super().write(vals)
        if must_notify:
            self._notify_parent_lines_changed(chatter_reason="Quantity/discount changed. Discount approvals reset if needed.")
        return res

    def unlink(self):
        orders = self.mapped("order_id")
        res = super().unlink()
        if orders:
            orders._on_discount_relevant_change(chatter_reason="Order lines changed (removed). Discount approvals reset if needed.")
        return res
