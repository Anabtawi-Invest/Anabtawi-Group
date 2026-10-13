# -*- coding: utf-8 -*-

import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _process_saved_order(self, draft):
        _logger.info(
            "[EMPLOYEE_DUE_LIMIT] server check: order %s (%s) draft=%s state=%s partner=%s (%s)",
            self.id, self.name, draft, self.state, self.partner_id.id, self.partner_id.name,
        )
        if not draft and self.state != "cancel":
            self._check_employee_due_limit()
        return super()._process_saved_order(draft)

    def _check_employee_due_limit(self):
        self.ensure_one()
        _logger.info(
            "[EMPLOYEE_DUE_LIMIT] order %s payments: %s",
            self.id,
            [
                (p.payment_method_id.name, p.payment_method_id.type, p.payment_method_id.journal_id.name, p.amount)
                for p in self.payment_ids
            ],
        )
        if not self.partner_id:
            _logger.info("[EMPLOYEE_DUE_LIMIT] order %s has no customer -> not checked", self.id)
            return
        amount = sum(
            self.payment_ids.filtered(
                lambda p: p.amount > 0 and p.payment_method_id.type == "pay_later"
            ).mapped("amount")
        )
        if amount <= 0:
            _logger.info(
                "[EMPLOYEE_DUE_LIMIT] order %s has no Customer Account (pay_later) payment -> not checked",
                self.id,
            )
            return
        status = self.partner_id._get_employee_due_limit_status(
            self.config_id, amount, exclude_order=self
        )
        if status["blocked"]:
            raise UserError(status["message"])
