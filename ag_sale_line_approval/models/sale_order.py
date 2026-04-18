from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    approval_line_count = fields.Integer(
        string="Approval Lines",
        compute="_compute_line_approval_summary",
    )
    pending_approval_line_count = fields.Integer(
        string="Pending Approval Lines",
        compute="_compute_line_approval_summary",
    )
    all_lines_approved = fields.Boolean(
        string="All Lines Approved",
        compute="_compute_line_approval_summary",
    )

    @api.depends(
        "order_line.approval_request_id",
        "order_line.approval_request_status",
        "order_line.has_requested_discount_change",
        "order_line.has_requested_price_change",
        "order_line.display_type",
    )
    def _compute_line_approval_summary(self):
        for order in self:
            approval_lines = order.order_line.filtered(lambda line: not line.display_type and line.approval_request_id)
            blocking_lines = order._get_blocking_approval_lines()
            order.approval_line_count = len(approval_lines)
            order.pending_approval_line_count = len(blocking_lines)
            order.all_lines_approved = not blocking_lines

    def _get_blocking_approval_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: not line.display_type and (
                line.has_requested_discount_change
                or line.has_requested_price_change
                or (
                    line.approval_request_id
                    and line.approval_request_status in ("new", "pending", "refused", "cancel")
                )
            )
        )

    def _raise_if_sale_line_approvals_block(self, operation_label):
        for order in self:
            blocking_lines = order._get_blocking_approval_lines()
            if not blocking_lines:
                continue
            line_names = ", ".join(blocking_lines.mapped("product_id.display_name"))
            raise UserError(
                _(
                    "You cannot %(operation)s while some sale order lines still need approval: %(lines)s",
                    operation=operation_label,
                    lines=line_names,
                )
            )

    def action_confirm(self):
        self._raise_if_sale_line_approvals_block(_("confirm this sales order"))
        return super().action_confirm()

    def _create_invoices(self, grouped=False, final=False, date=None):
        self._raise_if_sale_line_approvals_block(_("create an invoice"))
        return super()._create_invoices(grouped=grouped, final=final, date=date)
