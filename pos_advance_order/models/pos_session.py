# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

# Synthetic id for Closing Register UI only (not a real pos.payment.method).
ADVANCE_CLOSING_LINE_PAYMENT_METHOD_ID = -987654320
ADVANCE_DEPOSIT_CASH_CLOSING_LINE_PAYMENT_METHOD_ID = -987654321
ADVANCE_DEPOSIT_BANK_CLOSING_LINE_PAYMENT_METHOD_ID = -987654322


class PosSession(models.Model):
    _inherit = "pos.session"

    def _advance_orders_deposited_in_session(self):
        """Advance orders whose deposit entry was posted during this session window."""
        self.ensure_one()
        advance_orders = self.env["pos.advance.order"].sudo()
        end = self.stop_at or fields.Datetime.now()
        deposited = advance_orders.browse()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "not in", ("draft", "cancel")),
            ("advance_deposit_move_id.state", "=", "posted"),
        ]
        for adv_order in advance_orders.search(domain):
            pay_cfg = adv_order.from_pos_config_id or adv_order.pos_config_id
            if pay_cfg != self.config_id:
                continue
            move = adv_order.advance_deposit_move_id
            if move and self.start_at <= move.create_date <= end:
                deposited |= adv_order
        return deposited

    def _get_deposited_advance_summary(self):
        """Split deposited advances by liquidity type for closing register display."""
        self.ensure_one()
        summary = {"cash": 0.0, "bank": 0.0, "cash_count": 0, "bank_count": 0}
        if not self.config_id.enable_advance_order:
            return summary
        currency = self.currency_id
        cash_total = 0.0
        bank_total = 0.0
        cash_count = 0
        bank_count = 0
        for adv_order in self._advance_orders_deposited_in_session():
            amount = adv_order.advance_amount or 0.0
            if currency.is_zero(amount):
                continue
            pm = adv_order.pos_payment_method_id
            is_cash = (pm and pm.type == "cash") or (not pm and adv_order.payment_method == "cash")
            if is_cash:
                cash_total += amount
                cash_count += 1
            else:
                bank_total += amount
                bank_count += 1
        summary["cash"] = currency.round(cash_total)
        summary["bank"] = currency.round(bank_total)
        summary["cash_count"] = cash_count
        summary["bank_count"] = bank_count
        return summary

    def get_closing_control_data(self):
        """Split advance-on-completion amounts into their own Closing Register line.

        When the advance application uses the same method as main cash, Odoo would
        show the full order total under cash. We subtract those payment lines from
        their native bucket and add one informational row so cash count matches
        physical cash (e.g. 25) while advance (e.g. 5) is visible as 'Advance'.
        """
        data = super().get_closing_control_data()
        self.ensure_one()
        cfg = self.config_id
        if not cfg.enable_advance_order:
            return data

        deposited_summary = self._get_deposited_advance_summary()
        deposit_cash = deposited_summary["cash"]
        deposit_bank = deposited_summary["bank"]
        deposit_cash_count = deposited_summary["cash_count"]
        deposit_bank_count = deposited_summary["bank_count"]

        rounding = self.currency_id.rounding
        orders = self._get_closed_orders()
        advance_payments = self.env["pos.payment"]
        for order in orders:
            advance = order.advance_order_id
            if not advance or not advance.pos_config_id:
                continue
            remaining = advance.remaining_pos_order_id
            if not remaining or order.id != remaining.id:
                continue
            try:
                app_pm = advance._get_advance_application_payment_method(self)
            except UserError:
                continue
            for pay in order.payment_ids:
                if pay.payment_method_id != app_pm:
                    continue
                if float_is_zero(pay.amount, precision_rounding=rounding):
                    continue
                advance_payments |= pay

        default_cash = data.get("default_cash_details") or {}
        dc_id = default_cash.get("id")
        non_cash = list(data.get("non_cash_payment_methods") or [])

        if advance_payments:
            total_adv = sum(advance_payments.mapped("amount"))
            if not float_is_zero(total_adv, precision_rounding=rounding):
                for pay in advance_payments:
                    amt = pay.amount
                    pm = pay.payment_method_id
                    if dc_id and pm.id == dc_id:
                        default_cash["payment_amount"] = self.currency_id.round(
                            (default_cash.get("payment_amount") or 0.0) - amt
                        )
                        default_cash["amount"] = self.currency_id.round(
                            (default_cash.get("amount") or 0.0) - amt
                        )
                    else:
                        for row in non_cash:
                            if row.get("id") == pm.id:
                                row["amount"] = self.currency_id.round(row["amount"] - amt)
                                row["number"] = max(0, (row.get("number") or 0) - 1)
                                break
                non_cash.append({
                    "name": _("Advance (on completion)"),
                    "amount": total_adv,
                    "number": len(advance_payments),
                    "id": ADVANCE_CLOSING_LINE_PAYMENT_METHOD_ID,
                    "type": "pay_later",
                })

        if not float_is_zero(deposit_cash, precision_rounding=rounding):
            default_cash["payment_amount"] = self.currency_id.round(
                (default_cash.get("payment_amount") or 0.0) + deposit_cash
            )
            default_cash["amount"] = self.currency_id.round(
                (default_cash.get("amount") or 0.0) + deposit_cash
            )
            non_cash.append({
                "name": _("Cash Advance"),
                "amount": deposit_cash,
                "number": deposit_cash_count,
                "id": ADVANCE_DEPOSIT_CASH_CLOSING_LINE_PAYMENT_METHOD_ID,
                "type": "pay_later",
            })

        if not float_is_zero(deposit_bank, precision_rounding=rounding):
            non_cash.append({
                "name": _("Bank Advance"),
                "amount": deposit_bank,
                "number": deposit_bank_count,
                "id": ADVANCE_DEPOSIT_BANK_CLOSING_LINE_PAYMENT_METHOD_ID,
                "type": "pay_later",
            })

        non_cash = [
            row
            for row in non_cash
            if not float_is_zero(row.get("amount") or 0.0, precision_rounding=rounding)
        ]

        data["default_cash_details"] = default_cash or data.get("default_cash_details")
        data["non_cash_payment_methods"] = non_cash
        return data

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
