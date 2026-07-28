from odoo import models, _
from odoo.exceptions import UserError, AccessError


class PosSession(models.Model):
    _inherit = "pos.session"

    def _has_cash_move_access(self):
        if self.env.user._has_cash_move_permission():
            return True
        return any(
            session.employee_id.user_id._has_cash_move_permission()
            for session in self
            if session.employee_id.user_id
        )

    def try_cash_in_out(self, _type, amount, reason, partner_id, extras):
        if not self._has_cash_move_access():
            raise AccessError(_("You don't have the access rights to perform a cash in/out."))

        if self.env.user._has_cash_move_permission():
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
