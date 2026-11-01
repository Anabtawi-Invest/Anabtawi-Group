# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .check_payment_blocked_date import BLOCKED_WEEKDAY_FIELDS


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.onchange('payment_method_line_id')
    def _onchange_check_payment_entry_date(self):
        if self.is_check_payment and self.state == 'draft':
            if not self.check_date:
                self.check_date = self.date
            self.date = fields.Date.context_today(self)

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        check_line_ids = self._check_payment_method_line_ids(vals_list)
        for vals in vals_list:
            if vals.get('payment_method_line_id') in check_line_ids:
                if not vals.get('check_date'):
                    vals['check_date'] = vals.get('date') or today
                vals['date'] = today
        payments = super().create(vals_list)
        payments._force_check_payment_entry_date()
        payments._raise_if_blocked_check_date()
        return payments

    @api.onchange('date', 'check_date', 'payment_method_line_id')
    def _onchange_blocked_check_day(self):
        if not self.state or self.state == 'draft':
            self._raise_if_blocked_check_date()

    def write(self, vals):
        leaving_draft = self.browse()
        if vals.get('state') not in (None, 'draft', 'canceled', 'rejected'):
            leaving_draft = self.filtered(lambda payment: payment.state == 'draft')
        res = super().write(vals)
        if self.env.context.get('skip_check_payment_entry_date'):
            return res
        to_check = leaving_draft | self.filtered(lambda payment: payment.state == 'draft')
        if {'date', 'check_date', 'payment_method_line_id'} & set(vals):
            to_check |= self
        to_check._raise_if_blocked_check_date()
        self._force_check_payment_entry_date()
        return res

    def action_post(self):
        self._raise_if_blocked_check_date()
        self._force_check_payment_entry_date()
        return super().action_post()

    def _is_cheque_payment(self):
        self.ensure_one()
        if self.is_check_payment or self.check_number:
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
        if self.is_check_payment:
            return self.check_date or self.date
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
        today = fields.Date.context_today(self)
        to_fix = self.filtered(
            lambda payment: payment.is_check_payment and payment.state == 'draft' and payment.date != today
        )
        if to_fix:
            to_fix.with_context(skip_check_payment_entry_date=True).write({'date': today})

    @api.model
    def _check_payment_method_line_ids(self, vals_list):
        method_lines = self.env['account.payment.method.line'].browse([
            vals['payment_method_line_id']
            for vals in vals_list
            if vals.get('payment_method_line_id')
        ])
        return set(method_lines.filtered('is_check_payment').ids)
