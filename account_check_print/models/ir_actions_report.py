from odoo import models


class IrActionsReport(models.Model):
    """Select the check layout's custom paper size at render time."""

    _inherit = "ir.actions.report"

    def get_paperformat(self):
        """Use the active payment journal's layout paper format for checks."""
        self.ensure_one()
        if self.report_name == "account_check_print.report_check_document":
            active_ids = self.env.context.get("active_ids") or []
            payment_id = self.env.context.get("active_id") or (
                active_ids[0] if active_ids else False
            )
            if payment_id:
                payment = self.env["account.payment"].browse(payment_id).exists()
                if payment and payment.journal_id.check_layout_id.paperformat_id:
                    return payment.journal_id.check_layout_id.paperformat_id
        return super().get_paperformat()
