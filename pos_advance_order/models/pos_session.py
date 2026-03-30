# -*- coding: utf-8 -*-

from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def get_session_orders(self):
        orders = super().get_session_orders()
        # Do not aggregate advance-generated technical orders on session closing.
        if self.config_id.enable_advance_order:
            return orders.filtered(lambda o: not o.is_advance_generated)
        return orders

