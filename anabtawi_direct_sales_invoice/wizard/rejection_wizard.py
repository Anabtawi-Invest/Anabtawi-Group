from odoo import _, fields, models
from odoo.exceptions import UserError


class DirectSalesRejectionWizard(models.TransientModel):
    _name = "direct.sales.rejection.wizard"
    _description = "Direct Sales Warehouse Rejection"

    direct_invoice_id = fields.Many2one(
        "direct.sales.invoice",
        required=True,
        readonly=True,
    )
    rejection_reason = fields.Text(required=True)

    def action_reject(self):
        self.ensure_one()
        if not self.rejection_reason or not self.rejection_reason.strip():
            raise UserError(_("Enter a rejection reason."))
        return self.direct_invoice_id._reject_from_warehouse(self.rejection_reason)

