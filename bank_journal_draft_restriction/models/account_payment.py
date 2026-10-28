# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .account_move import GROUP_RESET_BANK_JOURNAL_DRAFT


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    bank_draft_restricted = fields.Boolean(compute='_compute_bank_draft_restricted')

    @api.depends('journal_id')
    @api.depends_context('uid')
    def _compute_bank_draft_restricted(self):
        allowed = self.env.su or self.env.user.has_group(GROUP_RESET_BANK_JOURNAL_DRAFT)
        for payment in self:
            payment.bank_draft_restricted = payment.journal_id.type == 'bank' and not allowed

    def action_draft(self):
        if not self.env.su and not self.env.user.has_group(GROUP_RESET_BANK_JOURNAL_DRAFT):
            if any(payment.journal_id.type == 'bank' for payment in self):
                raise UserError(_("You are not allowed to reset a bank journal entry to draft."))
        return super().action_draft()
