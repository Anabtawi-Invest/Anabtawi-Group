from odoo import _, fields, models
from odoo.exceptions import UserError


class DirectSalesWarehouseApprovalWizard(models.TransientModel):
    _name = "direct.sales.warehouse.approval.wizard"
    _description = "Direct Sales Warehouse Approval"

    direct_invoice_id = fields.Many2one(
        "direct.sales.invoice",
        required=True,
        readonly=True,
    )
    warehouse_comment = fields.Text(string="Warehouse Comment")

    def action_approve(self):
        self.ensure_one()
        if not self.direct_invoice_id:
            raise UserError(_("The direct invoice no longer exists."))
        return self.direct_invoice_id._approve_from_warehouse(
            partial=False,
            comment=self.warehouse_comment,
        )

