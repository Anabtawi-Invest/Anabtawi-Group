# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

GROUP_RESET_BANK_JOURNAL_DRAFT = 'bank_journal_draft_restriction.group_reset_bank_journal_draft'


class AccountMove(models.Model):
    _inherit = 'account.move'

    bank_draft_restricted = fields.Boolean(compute='_compute_bank_draft_restricted')

    @api.depends('journal_id')
    @api.depends_context('uid')
    def _compute_bank_draft_restricted(self):
        allowed = self.env.su or self.env.user.has_group(GROUP_RESET_BANK_JOURNAL_DRAFT)
        for move in self:
            move.bank_draft_restricted = move.journal_id.type == 'bank' and not allowed

    def _check_bank_journal_draft_access(self):
        if self.env.su or self.env.user.has_group(GROUP_RESET_BANK_JOURNAL_DRAFT):
            return
        if any(move.journal_id.type == 'bank' for move in self):
            raise UserError(_("You are not allowed to reset a bank journal entry to draft."))

    def button_draft(self):
        if not self.env.context.get('bank_journal_draft_internal'):
            self._check_bank_journal_draft_access()
        return super().button_draft()

    def button_cancel(self):
        return super(AccountMove, self.with_context(bank_journal_draft_internal=True)).button_cancel()
