# -*- coding: utf-8 -*-

from odoo import models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _process_saved_order(self, draft):
        if not draft and self.state != "cancel":
            self._check_employee_due_limit()
        return super()._process_saved_order(draft)

    def _check_employee_due_limit(self):
        self.ensure_one()
        if not self.partner_id:
            return
        amount = sum(
            self.payment_ids.filtered(
                lambda p: p.amount > 0 and p.payment_method_id.type == "pay_later"
            ).mapped("amount")
        )
        if amount <= 0:
            return
        status = self.partner_id._get_employee_due_limit_status(
            self.config_id, amount, exclude_order=self
        )
        if status["blocked"]:
            raise UserError(status["message"])
