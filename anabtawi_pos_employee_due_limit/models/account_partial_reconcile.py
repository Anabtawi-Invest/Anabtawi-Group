# -*- coding: utf-8 -*-

from odoo import api, models


class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    def _get_receivable_partners(self):
        lines = (self.debit_move_id | self.credit_move_id).filtered(
            lambda l: l.account_id.account_type == "asset_receivable"
        )
        return lines.partner_id

    @api.model_create_multi
    def create(self, vals_list):
        partials = super().create(vals_list)
        partials.sudo()._get_receivable_partners()._refresh_pos_customer_account_due()
        return partials

    def unlink(self):
        partners = self.sudo()._get_receivable_partners()
        res = super().unlink()
        partners._refresh_pos_customer_account_due()
        return res
