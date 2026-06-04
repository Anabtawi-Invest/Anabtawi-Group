from odoo import _, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _get_missing_customer_with_jofotara_error_domain(self):
        """Build domain for orders that should be updated.

        Condition:
        - No customer on order
        - JoFotara Error is set
        """
        error_field = None
        for candidate in ("l10n_jo_edi_pos_error", "pos_edi_error"):
            if candidate in self._fields:
                error_field = candidate
                break

        if not error_field:
            raise UserError(
                _(
                    "No JoFotara error field was found on POS Order. "
                    "Expected one of: l10n_jo_edi_pos_error, pos_edi_error."
                )
            )

        return [("partner_id", "=", False), (error_field, "!=", False)]

    def _get_orders_without_customer_count(self):
        return self.sudo().search_count(self._get_missing_customer_with_jofotara_error_domain())

    def action_open_default_customer_confirmation(self, partner_id=7252):
        count = self._get_orders_without_customer_count()
        return {
            "name": _("Confirm Default Customer Assignment"),
            "type": "ir.actions.act_window",
            "res_model": "pos.set.default.customer.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": partner_id,
                "default_records_count": count,
            },
        }

    def _assign_default_customer_to_empty_orders(self, partner_id=7252):
        """Set default customer on POS orders with no customer and JoFotara error."""
        partner = self.env["res.partner"].browse(partner_id).exists()
        if not partner:
            raise UserError(_("Default customer with ID %s was not found.") % partner_id)

        domain = self._get_missing_customer_with_jofotara_error_domain()
        orders_without_customer = self.sudo().search(domain)
        if orders_without_customer:
            orders_without_customer.write({"partner_id": partner.id})

        return len(orders_without_customer)
