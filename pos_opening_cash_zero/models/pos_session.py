# -*- coding: utf-8 -*-

from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def action_pos_session_open(self):
        """Set opening cash to 0 instead of carrying over the previous closing balance."""
        for session in self.filtered(lambda s: s.state == "opening_control"):
            if session.config_id.cash_control and not session.rescue:
                session.cash_register_balance_start = 0
            session.write({})
        return True

    def set_opening_control(self, cashbox_value, notes):
        """Always register zero as opening cash, regardless of UI input."""
        return super().set_opening_control(0, notes)

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
