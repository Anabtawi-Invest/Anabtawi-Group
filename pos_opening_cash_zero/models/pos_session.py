# -*- coding: utf-8 -*-

from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def action_pos_session_open(self):
        """Open session using the opening amount already set on the session."""
        return super().action_pos_session_open()

    def set_opening_control(self, cashbox_value, notes):
        """Persist the value entered by the user in Opening Control."""
        return super().set_opening_control(cashbox_value, notes)

    def pos_opening_cash_zero_reset(self):
        """Called from POS UI before showing the opening control popup."""
        self.ensure_one()
        if (
            self.state == "opening_control"
            and self.config_id.cash_control
            and not self.rescue
        ):
            self.cash_register_balance_start = 0
            self.write({})
        return 0
