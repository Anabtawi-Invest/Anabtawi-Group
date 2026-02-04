# -*- coding: utf-8 -*-

from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def get_session_orders(self):
        # Keep standard POS behavior (orders are accounted for at session closing).
        return super().get_session_orders()

