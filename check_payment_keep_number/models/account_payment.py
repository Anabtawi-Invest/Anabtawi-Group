# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    check_number_confirmed = fields.Boolean(copy=False, readonly=True)
    check_manual_sequencing = fields.Boolean(
        related=None,
        compute='_compute_check_manual_sequencing',
    )

    @api.depends('journal_id.check_manual_sequencing', 'check_number_confirmed')
    @api.depends_context('keep_check_number')
    def _compute_check_manual_sequencing(self):
        keep = self.env.context.get('keep_check_number')
        for payment in self:
            payment.check_manual_sequencing = (
                payment.journal_id.check_manual_sequencing
                and not (keep and payment.check_number_confirmed)
            )

    def write(self, vals):
        moved = self.filtered(lambda payment: payment.check_number_confirmed and (
            ('journal_id' in vals and payment.journal_id.id != vals['journal_id'])
            or ('payment_method_line_id' in vals
                and payment.payment_method_line_id.id != vals['payment_method_line_id'])
        ))
        res = super().write(vals)
        if moved:
            moved.check_number_confirmed = False
        return res

    def action_post(self):
        keep = self.filtered(
            lambda payment: payment.check_number_confirmed and payment.check_number and payment.state == 'draft'
        )
        if keep:
            super(AccountPayment, keep.with_context(keep_check_number=True)).action_post()
        rest = self - keep
        if rest:
            return super(AccountPayment, rest).action_post()

    def action_draft(self):
        self._confirm_issued_check_numbers()
        return super().action_draft()

    def action_cancel(self):
        self._confirm_issued_check_numbers()
        return super().action_cancel()

    def action_void_check(self):
        res = super().action_void_check()
        self.check_number_confirmed = False
        return res

    def _confirm_issued_check_numbers(self):
        self.filtered(
            lambda payment: payment.state in ('in_process', 'paid')
            and payment.check_number
            and payment.payment_method_code == 'check_printing'
            and payment.journal_id.check_manual_sequencing
        ).check_number_confirmed = True
