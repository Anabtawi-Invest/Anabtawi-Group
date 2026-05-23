# -*- coding: utf-8 -*-

from odoo import _, api, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _pos_purge_collect_moves(self):
        return self.env["pos.purge.service"]._collect_order_moves(self)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_draft_or_cancel(self):
        if self.env.context.get("pos_historical_purge"):
            return
        if any(order.state not in ("draft", "cancel") for order in self):
            raise UserError(
                _("In order to delete a sale, it must be new or cancelled.")
            )
