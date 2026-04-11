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

    @api.onchange("partner_id", "move_type")
    def _onchange_partner_vendor_customer_flags(self):
        """
        UI-friendly: if the user selects a wrong partner, clear it and show warning.
        The constraint above is still the real enforcement (imports/API/etc.).
        """
        for move in self:
            if not move.partner_id:
                continue

            if move.move_type in ("in_invoice", "in_refund", "in_receipt") and not move.partner_id.x_is_vendor:
                move.partner_id = False
                return {
                    "warning": {
                        "title": _("Not allowed"),
                        "message": _("This document is a Vendor Bill/Credit. Please select a contact marked as 'Is Vendor'."),
                    }
                }

            if move.move_type in ("out_invoice", "out_refund", "out_receipt") and not move.partner_id.x_is_customer:
                move.partner_id = False
                return {
                    "warning": {
                        "title": _("Not allowed"),
                        "message": _("This document is a Customer Invoice/Credit. Please select a contact marked as 'Is Customer'."),
                    }
                }
