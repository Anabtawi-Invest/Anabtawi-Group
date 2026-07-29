from odoo import _, api, Command, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class DirectSalesPartialApprovalWizard(models.TransientModel):
    _name = "direct.sales.partial.approval.wizard"
    _description = "Direct Sales Partial Warehouse Approval"

    direct_invoice_id = fields.Many2one(
        "direct.sales.invoice",
        required=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        "direct.sales.partial.approval.wizard.line",
        "wizard_id",
        string="Approval Quantities",
    )
    warehouse_comment = fields.Text(string="Warehouse Comment")

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        direct_invoice = self.env["direct.sales.invoice"].browse(
            self.env.context.get("default_direct_invoice_id")
        )
        if direct_invoice and "line_ids" in field_list:
            values["line_ids"] = [
                Command.create(
                    {
                        "direct_invoice_line_id": line.id,
                        "approved_quantity": min(line.quantity, line.free_quantity),
                    }
                )
                for line in direct_invoice.line_ids
            ]
        return values

    def action_apply(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("There are no product lines to approve."))
        if not any(line.approved_quantity > 0 for line in self.line_ids):
            raise UserError(_("Approve a positive quantity on at least one line."))
        for wizard_line in self.line_ids:
            source_line = wizard_line.direct_invoice_line_id
            if float_compare(
                wizard_line.approved_quantity,
                source_line.quantity,
                precision_rounding=source_line.product_uom_id.rounding,
            ) > 0:
                raise UserError(
                    _(
                        "Approved quantity cannot exceed requested quantity for %s.",
                        source_line.product_id.display_name,
                    )
                )
            source_line.with_context(direct_sales_warehouse_write=True).write(
                {"approved_quantity": wizard_line.approved_quantity}
            )
        return self.direct_invoice_id._approve_from_warehouse(
            partial=True,
            comment=self.warehouse_comment,
        )


class DirectSalesPartialApprovalWizardLine(models.TransientModel):
    _name = "direct.sales.partial.approval.wizard.line"
    _description = "Direct Sales Partial Approval Line"

    wizard_id = fields.Many2one(
        "direct.sales.partial.approval.wizard",
        required=True,
        ondelete="cascade",
    )
    direct_invoice_line_id = fields.Many2one(
        "direct.sales.invoice.line",
        required=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        related="direct_invoice_line_id.product_id",
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        related="direct_invoice_line_id.product_uom_id",
        readonly=True,
    )
    requested_quantity = fields.Float(
        related="direct_invoice_line_id.quantity",
        readonly=True,
    )
    free_quantity = fields.Float(
        related="direct_invoice_line_id.free_quantity",
        readonly=True,
    )
    forecast_quantity = fields.Float(
        related="direct_invoice_line_id.forecast_quantity",
        readonly=True,
    )
    approved_quantity = fields.Float(
        string="Approved Quantity",
        required=True,
        digits="Product Unit",
    )
    shortage_quantity = fields.Float(
        compute="_compute_shortage",
        digits="Product Unit",
    )

    @api.depends("requested_quantity", "approved_quantity")
    def _compute_shortage(self):
        for line in self:
            line.shortage_quantity = max(
                line.requested_quantity - line.approved_quantity,
                0.0,
            )

