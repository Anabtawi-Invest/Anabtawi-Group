# -*- coding: utf-8 -*-

import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _process_saved_order(self, draft):
        # New orders arrive already paid; check before marking them paid on the server.
        if not draft and self.state != "cancel":
            self._check_employee_due_limit()
        return super()._process_saved_order(draft)

    def _check_employee_due_limit(self):
        self.ensure_one()
        if not self.partner_id:
            return
        company = self.company_id or self.config_id.company_id
        start_utc, end_utc = self.partner_id._get_company_calendar_month_bounds(company)
        if not self.date_order or not (start_utc <= self.date_order < end_utc):
            _logger.info(
                "[EMPLOYEE_DUE_LIMIT] order %s date_order=%s is outside current month [%s, %s) -> not checked",
                self.id, self.date_order, start_utc, end_utc,
            )
            return
        amount = sum(
            self.payment_ids.filtered(
                lambda p: p.amount > 0 and p.payment_method_id.type == "pay_later"
            ).mapped("amount")
        )
        _logger.info(
            "[EMPLOYEE_DUE_LIMIT] server check order %s partner=%s pay_later_amount=%s payments=%s",
            self.id,
            self.partner_id.name,
            amount,
            [
                (p.payment_method_id.name, p.payment_method_id.type, p.amount)
                for p in self.payment_ids
            ],
        )
        if amount <= 0:
            return
        status = self.partner_id._get_employee_due_limit_status(
            self.config_id, amount, exclude_order=self
        )
        if status["blocked"]:
            raise UserError(status["message"])
