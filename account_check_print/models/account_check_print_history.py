from odoo import _, fields, models
from odoo.exceptions import AccessError


class AccountCheckPrintHistory(models.Model):
    """Keep an immutable audit trail of check lifecycle events."""

    _name = "account.check.print.history"
    _description = "Check Print History"
    _order = "event_date desc, id desc"
    _check_company_auto = True

    payment_id = fields.Many2one(
        "account.payment", required=True, ondelete="cascade", index=True,
        check_company=True,
    )
    company_id = fields.Many2one(related="payment_id.company_id", store=True)
    journal_id = fields.Many2one(related="payment_id.journal_id", store=True)
    check_number = fields.Char(required=True, index=True)
    event_type = fields.Selection(
        [("print", "Printed"), ("reprint", "Reprinted"), ("void", "Voided")],
        required=True,
        index=True,
    )
    event_date = fields.Datetime(required=True, default=fields.Datetime.now)
    user_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user,
        ondelete="restrict",
    )
    reason = fields.Text()

    def write(self, vals):
        """Prevent alteration of the audit trail."""
        raise AccessError(_("Check history entries cannot be modified."))

    def unlink(self):
        """Prevent deletion of the audit trail."""
        raise AccessError(_("Check history entries cannot be deleted."))
