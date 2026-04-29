# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import _, models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _get_receivable_account(self, payment_method):
        self.ensure_one()
        if payment_method.type == "pay_later" and self.config_id.pos_advance_receivable_account_id:
            return self.config_id.pos_advance_receivable_account_id
        return super()._get_receivable_account(payment_method)

    def get_session_orders(self):
        orders = super().get_session_orders()
        # Do not aggregate technical advance helper orders on session closing.
        return orders.filtered(lambda o: not o.is_advance_generated)

    def _get_advance_summary(self):
        self.ensure_one()
        advance_orders = self.env["pos.advance.order"].sudo().search([
            ("advance_session_id", "=", self.id),
            ("advance_move_id", "!=", False),
            ("advance_reverse_move_id", "=", False),
            ("state", "in", ("advance_paid", "fully_paid")),
        ])
        return {
            "cash": sum(advance_orders.filtered(lambda o: o.payment_method == "cash").mapped("advance_amount")),
            "bank": sum(advance_orders.filtered(lambda o: o.payment_method == "bank").mapped("advance_amount")),
        }

    def get_closing_control_data(self):
        data = super().get_closing_control_data()
        summary = self._get_advance_summary()
        data["advance_summary"] = summary
        if data.get("default_cash_details"):
            data["default_cash_details"]["advance_amount"] = summary["cash"]
            data["default_cash_details"]["amount"] += summary["cash"]
        return data

    def _create_account_move(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        data = super()._create_account_move(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs,
        )
        for session in self:
            session._create_advance_settlement_entries(data)
        return data

    def _create_advance_settlement_entries(self, data):
        self.ensure_one()
        advance_orders = self.order_ids.mapped("advance_order_id").filtered(lambda ao: ao.state == "fully_paid" and ao.advance_move_id)
        if not advance_orders:
            return

        amounts_by_accounts = defaultdict(float)
        for pos_order in self.order_ids.filtered(lambda po: po.advance_order_id and not po.is_advance_generated):
            advance_order = pos_order.advance_order_id
            applied_amount = sum(
                pos_order.payment_ids.filtered(lambda p: p.payment_method_id.type == "pay_later").mapped("amount")
            )
            if not applied_amount:
                continue
            liability_account = advance_order.pos_config_id.pos_advance_account_id
            if not liability_account:
                continue
            pay_later_payment = pos_order.payment_ids.filtered(lambda p: p.payment_method_id.type == "pay_later")[:1]
            receivable_account = (
                advance_order.pos_config_id.pos_advance_receivable_account_id
                or self._get_receivable_account(pay_later_payment.payment_method_id)
            )
            amounts_by_accounts[(liability_account.id, receivable_account.id)] += applied_amount

        if not amounts_by_accounts:
            return

        move_lines = self.env["account.move.line"]
        for (liability_account_id, receivable_account_id), amount in amounts_by_accounts.items():
            settlement_lines = self.env["account.move.line"].sudo().create([
                {
                    "move_id": self.move_id.id,
                    "name": _("Advance settlement %s") % self.name,
                    "account_id": liability_account_id,
                    "debit": amount,
                    "credit": 0.0,
                },
                {
                    "move_id": self.move_id.id,
                    "name": _("Advance settlement %s") % self.name,
                    "account_id": receivable_account_id,
                    "debit": 0.0,
                    "credit": amount,
                },
            ])
            move_lines |= settlement_lines.filtered(lambda line: line.account_id.id == receivable_account_id)

        receivable_account_ids = set(move_lines.mapped("account_id").ids)
        pay_later_move_lines = (data.get("pay_later_move_lines") or self.env["account.move.line"]).filtered(
            lambda line: line.account_id.id in receivable_account_ids
        )
        for receivable_account in move_lines.mapped("account_id"):
            lines_to_reconcile = (
                move_lines.filtered(lambda line: line.account_id == receivable_account)
                | pay_later_move_lines.filtered(lambda line: line.account_id == receivable_account and not line.reconciled)
            )
            if lines_to_reconcile and receivable_account.reconcile:
                lines_to_reconcile.sudo().reconcile()

