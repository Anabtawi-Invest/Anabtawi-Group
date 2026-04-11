from odoo import api, models, _
from odoo.exceptions import ValidationError

class AccountMove(models.Model):
    _inherit = "account.move"

    @api.constrains("partner_id", "move_type")
    def _check_partner_vendor_customer_flags(self):
        for move in self:
            if not move.partner_id:
                continue

            # Vendor documents
            if move.move_type in ("in_invoice", "in_refund", "in_receipt"):
                if not move.partner_id.x_is_vendor:
                    raise ValidationError(_(
                        "You can only select a contact marked as 'Is Vendor' for Vendor Bills/Credits."
                    ))

            # Customer documents
            if move.move_type in ("out_invoice", "out_refund", "out_receipt"):
                if not move.partner_id.x_is_customer:
                    raise ValidationError(_(
                        "You can only select a contact marked as 'Is Customer' for Customer Invoices/Credit Notes."
                    ))
