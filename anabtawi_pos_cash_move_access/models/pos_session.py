from odoo import models, _
from odoo.exceptions import UserError


class PosSession(models.Model):
    _inherit = "pos.session"

    def try_cash_in_out(self, _type, amount, reason, partner_id, extras):
        has_custom_cash_move_group = self.env.user.has_group(
            "anabtawi_pos_cash_move_access.group_pos_cash_in_out"
        )
        has_standard_cash_move_group = self.env.user.has_group("account.group_account_invoice")

        if not has_custom_cash_move_group or has_standard_cash_move_group:
            return super().try_cash_in_out(_type, amount, reason, partner_id, extras)

        sign = 1 if _type == "in" else -1
        sessions = self.filtered("cash_journal_id")
        if not sessions:
            raise UserError(_("There is no cash payment method for this PoS Session"))

        vals_list = [
            self._prepare_account_bank_statement_line_vals(
                session, sign, amount, reason, partner_id, extras
            )
            for session in sessions
        ]

        self.env["account.bank.statement.line"].with_context(
            no_retrieve_partner=True
        ).sudo().create(vals_list)
