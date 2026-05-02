# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import fields, models


class PosSession(models.Model):
    _inherit = "pos.session"

    def get_session_orders(self):
        orders = super().get_session_orders()
        # Do not aggregate advance-generated technical orders on session closing.
        if self.config_id.enable_advance_order:
            return orders.filtered(lambda o: not o.is_advance_generated)
        return orders

    def _advance_orders_deposited_in_session(self):
        """Advance orders whose deposit move was booked while this session was open.

        Matches the POS configuration where the deposit was taken (`from POS` else picking POS)
        so closing control and printed sale details reconcile physical liquidity with deposits
        posted outside POS order flows.
        """
        self.ensure_one()
        Advance = self.env["pos.advance.order"].sudo()
        cfg = self.config_id
        end = self.stop_at or fields.Datetime.now()
        deposit_domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "not in", ("draft", "cancel")),
            ("advance_deposit_move_id.state", "=", "posted"),
        ]
        deposited = Advance.browse()
        for order in Advance.search(deposit_domain):
            pay_cfg = order.from_pos_config_id or order.pos_config_id
            if pay_cfg != cfg:
                continue
            move = order.advance_deposit_move_id
            if move and self.start_at <= move.create_date <= end:
                deposited |= order
        return deposited

    def _get_advance_summary(self):
        """Return advance deposit liquidity attributed to this session (POS journal-based).

        - ``cash`` / ``bank``: totals for compatibility with sale details report rows.
        - ``by_payment_method``: {pos.payment.method.id: amount} so closing control can extend
          the matching non-cash payment row (bank journals).
        """
        self.ensure_one()
        outcome = {"cash": 0.0, "bank": 0.0, "by_payment_method": {}}
        if not self.config_id.enable_advance_order:
            return outcome
        currency = self.currency_id
        by_pm = defaultdict(float)
        cash_total = 0.0
        for order in self._advance_orders_deposited_in_session():
            amt = order.advance_amount or 0.0
            if currency.is_zero(amt):
                continue
            pm = order.pos_payment_method_id
            if pm and pm.type == "cash":
                cash_total += amt
            elif pm and pm.type == "bank":
                by_pm[pm.id] += amt
            elif order.payment_method == "cash":
                cash_total += amt
            else:
                fallback_bank = self.payment_method_ids.filtered(lambda m: m.type == "bank")[:1]
                if fallback_bank:
                    by_pm[fallback_bank.id] += amt
        outcome["cash"] = currency.round(cash_total)
        outcome["bank"] = currency.round(sum(by_pm.values()))
        outcome["by_payment_method"] = {pid: currency.round(am) for pid, am in by_pm.items()}
        return outcome

    def get_closing_control_data(self):
        data = super().get_closing_control_data()
        if not self.config_id.enable_advance_order:
            return data
        summary = self._get_advance_summary()
        cur = self.currency_id
        if cur.is_zero(summary["cash"]) and not summary["by_payment_method"]:
            return data

        data = dict(data)

        cash_extra = summary["cash"]
        if not cur.is_zero(cash_extra) and data.get("default_cash_details"):
            dc = dict(data["default_cash_details"])
            dc["amount"] = cur.round(dc["amount"] + cash_extra)
            dc["payment_amount"] = cur.round(dc["payment_amount"] + cash_extra)
            data["default_cash_details"] = dc

        pm_extra = summary["by_payment_method"]
        if pm_extra:
            patched = []
            for row in data.get("non_cash_payment_methods") or []:
                row_copy = dict(row)
                pid = row_copy["id"]
                extra = pm_extra.get(pid, 0.0)
                if not cur.is_zero(extra):
                    row_copy["amount"] = cur.round(row_copy["amount"] + extra)
                patched.append(row_copy)
            data["non_cash_payment_methods"] = patched

        return data
