from odoo import _, fields, models
from odoo.exceptions import AccessError


class AccountMove(models.Model):
    _inherit = "account.move"

    direct_sales_invoice_id = fields.Many2one(
        "direct.sales.invoice",
        string="Direct Sales Document",
        readonly=True,
        copy=False,
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Pricelist Used",
        readonly=True,
        copy=True,
        tracking=True,
        check_company=True,
    )
    pickup_warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Pickup Warehouse",
        readonly=True,
        copy=False,
        tracking=True,
        check_company=True,
    )
    warehouse_approved_by = fields.Many2one(
        "res.users",
        string="Warehouse Approved By",
        readonly=True,
        copy=False,
    )
    warehouse_approved_at = fields.Datetime(
        string="Warehouse Approval Date", readonly=True, copy=False
    )
    direct_sales_picking_ids = fields.Many2many(
        "stock.picking",
        "account_move_direct_sales_picking_rel",
        "move_id",
        "picking_id",
        string="Direct Sales Pickings",
        readonly=True,
        copy=False,
        check_company=True,
    )
    direct_sales_picking_count = fields.Integer(
        compute="_compute_direct_sales_picking_count"
    )

    def write(self, vals):
        protected = {
            "direct_sales_invoice_id",
            "pricelist_id",
            "pickup_warehouse_id",
            "warehouse_approved_by",
            "warehouse_approved_at",
            "direct_sales_picking_ids",
        }
        if (
            protected.intersection(vals)
            and (
                vals.get("direct_sales_invoice_id")
                or self.filtered("direct_sales_invoice_id")
            )
            and not self.env.context.get("direct_sales_link_write")
        ):
            raise AccessError(
                _(
                    "Direct Sales invoice references are immutable after invoice creation."
                )
            )
        return super().write(vals)

    def _compute_direct_sales_picking_count(self):
        for move in self:
            move.direct_sales_picking_count = len(move.direct_sales_picking_ids)

    def action_post(self):
        result = super().action_post()
        documents = self.filtered("direct_sales_invoice_id").mapped(
            "direct_sales_invoice_id"
        )
        if documents:
            documents._complete_activities(
                "anabtawi_direct_sales_invoice.mail_activity_direct_accounting_review"
            )
            documents._update_completion_state()
        return result

    def action_view_direct_sales_document(self):
        self.ensure_one()
        return {
            "name": _("Direct Sales Document"),
            "type": "ir.actions.act_window",
            "res_model": "direct.sales.invoice",
            "view_mode": "form",
            "res_id": self.direct_sales_invoice_id.id,
        }

    def action_view_direct_sales_pickings(self):
        self.ensure_one()
        action = {
            "name": _("Direct Sales Pickings"),
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", self.direct_sales_picking_ids.ids)],
            "context": {"create": False},
        }
        if len(self.direct_sales_picking_ids) == 1:
            action.update(
                {"view_mode": "form", "res_id": self.direct_sales_picking_ids.id}
            )
        return action


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    direct_invoice_line_id = fields.Many2one(
        "direct.sales.invoice.line",
        string="Direct Sales Line",
        readonly=True,
        copy=False,
        index=True,
        ondelete="restrict",
        check_company=True,
    )

    def write(self, vals):
        if (
            "direct_invoice_line_id" in vals
            and (
                vals.get("direct_invoice_line_id")
                or self.filtered("direct_invoice_line_id")
            )
            and not self.env.context.get("direct_sales_link_write")
        ):
            raise AccessError(
                _("Direct Sales invoice-line references are immutable after creation.")
            )
        return super().write(vals)
