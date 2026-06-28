from odoo import fields, models


class AccountCheckVoidWizard(models.TransientModel):
    """Collect the required audit reason before voiding a check."""

    _name = "account.check.void.wizard"
    _description = "Void Check"

    payment_id = fields.Many2one("account.payment", required=True, readonly=True)
    check_number = fields.Char(related="payment_id.check_number", readonly=True)
    reason = fields.Text(required=True)

    def action_confirm(self):
        """Void the selected check and close the dialog."""
        self.ensure_one()
        self.payment_id._void_check(self.reason)
        return {"type": "ir.actions.act_window_close"}

