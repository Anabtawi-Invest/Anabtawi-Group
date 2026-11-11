# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .check_payment_blocked_date import BLOCKED_WEEKDAY_FIELDS


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _applies_check_entry_date(self):
        """True when the payment method line is marked as a check."""
        self.ensure_one()
        return bool(self.payment_method_line_id.is_check_payment)

    def _uses_separate_check_date(self):
        self.ensure_one()
        return self._applies_check_entry_date() and 'check_date' in self._fields

    def action_post(self):
        self._raise_if_blocked_check_date()
        self._force_check_payment_entry_date()
        return super().action_post()

    def _is_cheque_payment(self):
        self.ensure_one()
        if self.payment_method_line_id.is_check_payment:
            return True
        if 'check_number' in self._fields and self.check_number:
            return True
        code = self.payment_method_code or self.payment_method_line_id.code or ''
        if code == 'check_printing' or 'check' in code:
            return True
        name = self.payment_method_line_id.name or ''
        lowered = name.casefold()
        return 'check' in lowered or 'cheque' in lowered or 'شيك' in name

    def _cheque_date_to_restrict(self):
        """Date chosen for the cheque.

        Check Date is the printed date when that field is in use.
        A standard Checks payment uses the Date field shown on the form.
        """
        self.ensure_one()
        if not self._is_cheque_payment():
            return False
        if self._uses_separate_check_date() and self.check_date:
            return self.check_date
        return self.date

    def _raise_if_blocked_check_date(self):
        for payment in self:
            cheque_date = payment._cheque_date_to_restrict()
            if not cheque_date:
                continue
            weekday_field = BLOCKED_WEEKDAY_FIELDS[cheque_date.weekday()]
            companies = (payment.company_id | payment.company_id.root_id | self.env.company).sudo()
            if any(company[weekday_field] for company in companies):
                raise UserError(_("You cannot cash a check on this day."))

    def _force_check_payment_entry_date(self):
        """Set the journal entry date to today only when confirming a check payment."""
        today = fields.Date.context_today(self)
        to_fix = self.filtered(
            lambda payment: payment._applies_check_entry_date() and payment.state == 'draft' and payment.date != today
        )
        if to_fix:
            to_fix.write({'date': today})
