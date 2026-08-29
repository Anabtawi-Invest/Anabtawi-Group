from odoo import models, _
from odoo.exceptions import UserError


class PosSession(models.Model):
    _inherit = "pos.session"

    def _close_ip_block_response(self):
        self.ensure_one()
        allowed, _client_ip, _token, message = self.config_id._check_close_allowed()
        if allowed:
            return False
        return {
            "successful": False,
            "title": _("Close Register Restricted"),
            "message": message,
            "redirect": False,
        }

    def _raise_if_close_ip_forbidden(self):
        for session in self:
            allowed, _client_ip, _token, message = session.config_id._check_close_allowed()
            if not allowed:
                raise UserError(message)

    def check_close_allowed_ip(self):
        self.ensure_one()
        allowed, client_ip, _token, message = self.config_id._check_close_allowed()
        return {
            "allowed": allowed,
            "ip": client_ip or "",
            "message": message,
        }

    def _cannot_close_session(self, bank_payment_method_diffs=None):
        result = super()._cannot_close_session(bank_payment_method_diffs)
        if result:
            return result
        return self._close_ip_block_response()

    def update_closing_control_state_session(self, notes):
        self._raise_if_close_ip_forbidden()
        return super().update_closing_control_state_session(notes)

    def action_pos_session_closing_control(
        self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None
    ):
        self._raise_if_close_ip_forbidden()
        return super().action_pos_session_closing_control(
            balancing_account, amount_to_balance, bank_payment_method_diffs
        )

    def _validate_session(
        self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None
    ):
        self._raise_if_close_ip_forbidden()
        return super()._validate_session(
            balancing_account, amount_to_balance, bank_payment_method_diffs
        )