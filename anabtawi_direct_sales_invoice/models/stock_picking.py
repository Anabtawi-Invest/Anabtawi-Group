from odoo import _, fields, models
from odoo.exceptions import AccessError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    direct_invoice_id = fields.Many2one(
        "direct.sales.invoice",
        string="Direct Sales Invoice",
        copy=False,
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    customer_invoice_id = fields.Many2one(
        "account.move",
        string="Customer Invoice",
        copy=False,
        index=True,
        ondelete="set null",
        check_company=True,
    )
    pickup_customer_id = fields.Many2one(
        related="direct_invoice_id.partner_id",
        string="Pickup Customer",
        store=True,
        index=True,
    )
    direct_sales_warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Pickup Warehouse",
        copy=False,
        index=True,
        check_company=True,
    )
    direct_sales_stage = fields.Selection(
        [
            ("preparation", "Preparation to Dispatch"),
            ("release", "Customer Release"),
            ("return", "Customer Return"),
        ],
        string="Direct Sales Stage",
        copy=False,
        index=True,
    )

    def write(self, vals):
        protected = {
            "direct_invoice_id",
            "customer_invoice_id",
            "direct_sales_warehouse_id",
            "direct_sales_stage",
        }
        if (
            protected.intersection(vals)
            and (
                vals.get("direct_invoice_id")
                or self.filtered("direct_invoice_id")
            )
            and not self.env.context.get("direct_sales_link_write")
        ):
            raise AccessError(
                _(
                    "Direct Sales picking links are immutable outside the controlled "
                    "invoice and return workflows."
                )
            )
        return super().write(vals)

    def _create_backorder_picking(self):
        backorder = super()._create_backorder_picking()
        if self.direct_invoice_id:
            backorder.with_context(direct_sales_link_write=True).write(
                {
                    "direct_invoice_id": self.direct_invoice_id.id,
                    "customer_invoice_id": self.customer_invoice_id.id,
                    "direct_sales_warehouse_id": self.direct_sales_warehouse_id.id,
                    "direct_sales_stage": self.direct_sales_stage,
                }
            )
        return backorder

    def _action_done(self):
        result = super()._action_done()
        for picking in self.filtered(
            lambda item: item.direct_invoice_id and item.state == "done"
        ):
            picking.direct_invoice_id._sync_after_picking_done(picking)
        return result

    def action_cancel(self):
        result = super().action_cancel()
        allocations = self.move_ids.mapped("direct_sales_allocation_id")
        if allocations:
            allocations.with_context(direct_sales_warehouse_write=True).write(
                {"state": "cancelled"}
            )
        return result

    def action_view_direct_sales_document(self):
        self.ensure_one()
        return {
            "name": _("Direct Sales Document"),
            "type": "ir.actions.act_window",
            "res_model": "direct.sales.invoice",
            "view_mode": "form",
            "res_id": self.direct_invoice_id.id,
        }

    def action_view_customer_invoice(self):
        self.ensure_one()
        return {
            "name": _("Customer Invoice"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.customer_invoice_id.id,
        }
