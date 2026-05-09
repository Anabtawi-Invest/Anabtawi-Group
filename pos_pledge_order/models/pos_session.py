# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, models
import logging

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'

    def get_session_orders(self):
        """Exclude legacy technical pledge orders from session aggregates."""
        orders = super().get_session_orders()
        return orders.filtered(lambda o: not o.is_pledge_generated)

    def _get_closed_orders(self):
        orders = super()._get_closed_orders()
        return orders.filtered(lambda o: not o.is_pledge_generated)

    def _get_pledge_deposit_closing_summary(self):
        """Pledge deposits posted as JEs (not in pos.payment): allocate by journal vs POS payment methods."""
        self.ensure_one()
        outcome = {"cash": 0.0, "by_pm": defaultdict(float)}
        cur = self.currency_id
        for order in self._get_closed_orders():
            move = order.sudo().pledge_deposit_move_id
            if not move or move.state != "posted":
                continue
            amt = order.total_pledge_amount or 0.0
            if cur.is_zero(amt):
                continue
            mj = move.journal_id
            matched = False
            for pm in self.payment_method_ids:
                if pm.journal_id != mj:
                    continue
                matched = True
                if pm.type == "cash":
                    outcome["cash"] += amt
                else:
                    outcome["by_pm"][pm.id] += amt
                break
            if not matched:
                _logger.warning(
                    "[PLEDGE] Session %s: pledge move journal %s does not match any payment method journal; "
                    "pledge %s skipped in closing summary.",
                    self.id,
                    mj.display_name,
                    order.display_name,
                )
        outcome["cash"] = cur.round(outcome["cash"])
        outcome["by_pm"] = {pid: cur.round(a) for pid, a in outcome["by_pm"].items()}
        return outcome

    @api.depends(
        'payment_method_ids',
        'order_ids',
        'cash_register_balance_start',
        'cash_register_balance_end_real',
        'statement_line_ids.amount',
        'order_ids.pledge_deposit_move_id',
        'order_ids.total_pledge_amount',
    )
    def _compute_cash_balance(self):
        super()._compute_cash_balance()
        for session in self:
            extra = session._get_pledge_deposit_closing_summary()["cash"]
            if session.currency_id.is_zero(extra):
                continue
            session.cash_register_balance_end = session.currency_id.round(
                session.cash_register_balance_end + extra
            )
            session.cash_register_difference = session.currency_id.round(
                session.cash_register_balance_end_real - session.cash_register_balance_end
            )

    def _invalidate_open_sessions_cash_balance(self):
        """When pledge JEs change outside payment flow, refresh theoretical cash."""
        sessions = self.env["pos.session"].sudo().search(
            [
                ("config_id", "in", self.mapped("config_id").ids),
                ("company_id", "in", self.mapped("company_id").ids),
                ("state", "in", ("opened", "closing_control")),
            ]
        )
        if sessions:
            sessions.invalidate_recordset(
                ["cash_register_balance_end", "cash_register_difference"]
            )

    def get_closing_control_data(self):
        data = super().get_closing_control_data()
        summary = self._get_pledge_deposit_closing_summary()
        cur = self.currency_id
        cash_extra = summary["cash"]
        by_pm = summary["by_pm"]

        if data.get("default_cash_details"):
            dc = dict(data["default_cash_details"])
            dc["pledge_payment_amount"] = cash_extra
            if not cur.is_zero(cash_extra):
                dc["amount"] = cur.round(dc["amount"] + cash_extra)
            data["default_cash_details"] = dc

        patched = []
        for row in data.get("non_cash_payment_methods") or []:
            r = dict(row)
            adv = cur.round(by_pm.get(row["id"], 0.0))
            r["pledge_payment_amount"] = adv
            if not cur.is_zero(adv):
                r["amount"] = cur.round(r["amount"] + adv)
            patched.append(r)
        data["non_cash_payment_methods"] = patched
        return data
