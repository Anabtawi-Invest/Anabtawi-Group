# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models
from odoo.tools import float_is_zero


class PosSession(models.Model):
    _inherit = "pos.session"

    def _accumulate_amounts(self, data):
        data = super()._accumulate_amounts(data)
        combine = data.get("combine_receivables_pay_later")
        if not combine:
            data["combine_receivables_pay_later_advance"] = {}
            return data

        amounts_fn = lambda: {"amount": 0.0, "amount_converted": 0.0}
        combine_advance = defaultdict(amounts_fn)
        rounding = self.currency_id.rounding

        for order in self._get_closed_orders():
            if order.is_invoiced:
                continue
            advance = order.advance_order_id
            if not advance or not advance.pos_config_id.pos_advance_receivable_account_id:
                continue
            for payment in order.payment_ids:
                pm = payment.payment_method_id
                if pm.type != "pay_later" or pm.split_transactions:
                    continue
                amount = payment.amount
                if float_is_zero(amount, precision_rounding=rounding):
                    continue
                date = payment.payment_date
                combine_advance[pm] = self._update_amounts(
                    combine_advance[pm], {"amount": amount}, date
                )
                combine[pm] = self._update_amounts(
                    combine[pm], {"amount": -amount}, date
                )

        for pm in list(combine.keys()):
            if float_is_zero(combine[pm]["amount"], precision_rounding=rounding):
                del combine[pm]
        for pm in list(combine_advance.keys()):
            if float_is_zero(combine_advance[pm]["amount"], precision_rounding=rounding):
                del combine_advance[pm]

        data["combine_receivables_pay_later_advance"] = dict(combine_advance)
        return data

    def _get_combine_advance_pay_later_receivable_vals(
        self, payment_method, amount, amount_converted
    ):
        acc = self.config_id.pos_advance_receivable_account_id
        partial_vals = {
            "account_id": acc.id,
            "move_id": self.move_id.id,
            "name": "%s - %s (Advance)" % (self.name, payment_method.name),
            "display_type": "payment_term",
        }
        return self._debit_amounts(partial_vals, amount, amount_converted)

    def _create_pay_later_receivable_lines(self, data):
        MoveLine = data.get("MoveLine")
        combine_receivables_pay_later = data.get("combine_receivables_pay_later") or {}
        combine_advance = data.get("combine_receivables_pay_later_advance") or {}
        split_receivables_pay_later = data.get("split_receivables_pay_later")
        vals = []

        rounding = self.currency_id.rounding
        for payment_method, amounts in combine_receivables_pay_later.items():
            if float_is_zero(amounts["amount"], precision_rounding=rounding):
                continue
            vals.append(
                self._get_combine_receivable_vals(
                    payment_method, amounts["amount"], amounts["amount_converted"]
                )
            )
        for payment_method, amounts in combine_advance.items():
            if float_is_zero(amounts["amount"], precision_rounding=rounding):
                continue
            vals.append(
                self._get_combine_advance_pay_later_receivable_vals(
                    payment_method, amounts["amount"], amounts["amount_converted"]
                )
            )
        for payment, amounts in split_receivables_pay_later.items():
            vals.append(
                self._get_split_receivable_vals(
                    payment, amounts["amount"], amounts["amount_converted"]
                )
            )
        for val in vals:
            val["no_followup"] = False
        data["pay_later_move_lines"] = MoveLine.create(vals)
        return data

    def _get_split_receivable_vals(self, payment, amount, amount_converted):
        order = payment.pos_order_id
        advance = order.advance_order_id
        if advance and advance.pos_config_id.pos_advance_receivable_account_id:
            acc = advance.pos_config_id.pos_advance_receivable_account_id
            accounting_partner = self.env["res.partner"]._find_accounting_partner(
                payment.partner_id
            )
            if not accounting_partner:
                return super()._get_split_receivable_vals(
                    payment, amount, amount_converted
                )
            partial_vals = {
                "account_id": acc.id,
                "move_id": self.move_id.id,
                "partner_id": accounting_partner.id,
                "name": "%s - %s" % (self.name, payment.payment_method_id.name),
            }
            return self._debit_amounts(partial_vals, amount, amount_converted)
        return super()._get_split_receivable_vals(payment, amount, amount_converted)
