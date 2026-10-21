# -*- coding: utf-8 -*-

from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _validate_session(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        res = super()._validate_session(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs,
        )
        partners = self.sudo().order_ids.filtered(
            lambda o: any(p.payment_method_id.type == "pay_later" for p in o.payment_ids)
        ).partner_id
        partners._refresh_pos_customer_account_due()
        return res
