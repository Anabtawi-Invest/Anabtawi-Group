from odoo import fields, models, _


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        string="Sale Order Line",
        copy=False,
        readonly=True,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sale Order",
        related="sale_order_line_id.order_id",
        store=True,
        readonly=True,
    )
    sale_line_change_type = fields.Selection(
        selection=[
            ("discount", "Discount"),
            ("price_override", "Price Override"),
            ("mixed", "Discount and Price Override"),
        ],
        string="Sale Line Change Type",
        copy=False,
        readonly=True,
    )
    sale_line_requested_discount = fields.Float(
        string="Requested Discount (%)",
        copy=False,
        readonly=True,
    )
    sale_line_requested_price_unit = fields.Float(
        string="Requested Unit Price",
        copy=False,
        readonly=True,
    )
    sale_line_changes_applied = fields.Boolean(copy=False, readonly=True)

    def _apply_sale_line_changes(self):
        for request in self.filtered(lambda req: req.request_status == "approved" and req.sale_order_line_id and not req.sale_line_changes_applied):
            line = request.sale_order_line_id.exists()
            if not line:
                request.sudo().write({"sale_line_changes_applied": True})
                continue

            values = {}
            line_reset_vals = {}

            if request.sale_line_change_type in ("discount", "mixed"):
                values["discount"] = request.sale_line_requested_discount
                line_reset_vals.update({
                    "requested_discount": 0.0,
                    "has_requested_discount_change": False,
                })
            if request.sale_line_change_type in ("price_override", "mixed"):
                values.update({
                    "price_unit": request.sale_line_requested_price_unit,
                    "technical_price_unit": request.sale_line_requested_price_unit,
                })
                line_reset_vals.update({
                    "requested_price_unit": 0.0,
                    "has_requested_price_change": False,
                })

            if values:
                line.with_context(ag_skip_sale_line_approval=True).write(values)
            if line_reset_vals:
                line.with_context(ag_skip_sale_line_approval=True).write(line_reset_vals)
            request.sudo().write({"sale_line_changes_applied": True})

    def action_open_sale_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Sale Order"),
            "res_model": "sale.order",
            "view_mode": "form",
            "res_id": self.sale_order_id.id,
            "target": "current",
        }

    def action_approve(self, approver=None):
        result = super().action_approve(approver=approver)
        self.filtered(lambda request: request.request_status == "approved")._apply_sale_line_changes()
        return result

    def _action_force_approval(self):
        result = super()._action_force_approval()
        self.filtered(lambda request: request.request_status == "approved")._apply_sale_line_changes()
        return result
