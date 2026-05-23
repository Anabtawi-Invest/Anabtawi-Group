# -*- coding: utf-8 -*-

from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _pos_purge_can_delete(self):
        self.ensure_one()
        return not self.order_ids
