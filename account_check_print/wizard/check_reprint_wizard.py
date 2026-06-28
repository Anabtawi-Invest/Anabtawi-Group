from odoo import fields, models


class AccountCheckReprintWizard(models.TransientModel):
    """Collect the required audit reason before reprinting a check."""

    _name = "account.check.reprint.wizard"
    _description = "Reprint Check"

    payment_id = fields.Many2one("account.payment", required=True, readonly=True)
    check_number = fields.Char(related="payment_id.check_number", readonly=True)
    reason = fields.Text(required=True)

    def action_confirm(self):
        """Audit the reprint and return the check PDF action."""
        self.ensure_one()
        return self.payment_id._reprint_check(self.reason)

