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

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_check_payment_entry_date'):
            self._force_check_payment_entry_date()
            to_check = self.filtered(lambda payment: payment.state == 'draft')
            if 'check_date' in vals:
                to_check |= self
            to_check._raise_if_blocked_check_date()
        return res

    def action_post(self):
        self._force_check_payment_entry_date()
        self._raise_if_blocked_check_date()
        return super().action_post()

    def _raise_if_blocked_check_date(self):
        payments = self.filtered(lambda payment: payment.is_check_payment and payment.check_date)
        if not payments:
            return
        for payment in payments:
            weekday_field = BLOCKED_WEEKDAY_FIELDS[payment.check_date.weekday()]
            if payment.company_id[weekday_field]:
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
