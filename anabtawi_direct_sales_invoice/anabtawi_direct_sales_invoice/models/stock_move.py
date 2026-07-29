from odoo import _, fields, models
from odoo.exceptions import AccessError


class StockMove(models.Model):
    _inherit = "stock.move"

    direct_invoice_line_id = fields.Many2one(
        "direct.sales.invoice.line",
        string="Direct Sales Line",
        copy=False,
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    direct_sales_invoice_id = fields.Many2one(
        related="direct_invoice_line_id.direct_invoice_id",
        string="Direct Sales Document",
        store=True,
        index=True,
    )
    direct_sales_allocation_id = fields.Many2one(
        "direct.sales.invoice.allocation",
        string="Direct Sales Allocation",
        copy=False,
        index=True,
        ondelete="restrict",
        check_company=True,
    )

    def write(self, vals):
        if (
            {
                "direct_invoice_line_id",
                "direct_sales_allocation_id",
            }.intersection(vals)
            and (
                vals.get("direct_invoice_line_id")
                or self.filtered("direct_invoice_line_id")
            )
            and not self.env.context.get("direct_sales_link_write")
        ):
            raise AccessError(
                _(
                    "Direct Sales stock-move links are immutable outside controlled "
                    "stock workflows."
                )
            )
        return super().write(vals)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    direct_invoice_line_id = fields.Many2one(
        related="move_id.direct_invoice_line_id",
        string="Direct Sales Line",
        store=True,
        index=True,
    )
