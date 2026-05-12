# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models
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

    def _pledge_deposit_voided_by_return_this_session(self, order):
        """True if pledge lines exist, all returned, and reversal move was posted during this session."""
        self.ensure_one()
        end = self.stop_at or fields.Datetime.now()
        lines = order.sudo().advance_pledge_line_ids
        if not lines or not all(l.state == "returned" for l in lines):
            return False
        ret = lines[:1].return_move_id
        if not ret or ret.state != "posted":
            return False
        return bool(self.start_at <= ret.create_date <= end)

    def _iter_pledge_journal_payment_split(self, amount, move):
        """Yield ('cash', amt) or ('pm', pm_id, amt) for a pledge deposit move."""
        self.ensure_one()
        cur = self.currency_id
        if cur.is_zero(amount or 0.0):
            return
        mj = move.journal_id
        for pm in self.payment_method_ids:
            if pm.journal_id != mj:
                continue
            if pm.type == "cash":
                yield ("cash", amount)
            else:
                yield ("pm", pm.id, amount)
            return
        _logger.warning(
            "[PLEDGE] Session %s: pledge move journal %s does not match any payment method journal; "
            "pledge %s skipped in closing summary.",
            self.id,
            mj.display_name,
            move.display_name,
        )

    def _get_pledge_deposit_closing_summary(self):
        """Pledge deposits posted as JEs (not in pos.payment): allocate by journal vs POS payment methods.

        - Skips deposits that were fully returned (reversal posted) in the same session (net 0 in drawer).
        - Subtracts pledge reversals posted this session when the original sale was in a **prior**
          session (cash left the drawer during this session).
        """
        self.ensure_one()
        outcome = {"cash": 0.0, "by_pm": defaultdict(float)}
        cur = self.currency_id
        end = self.stop_at or fields.Datetime.now()

        for order in self._get_closed_orders():
            move = order.sudo().pledge_deposit_move_id
            if not move or move.state != "posted":
                continue
            if self._pledge_deposit_voided_by_return_this_session(order):
                continue
            amt = order.total_pledge_amount or 0.0
            for part in self._iter_pledge_journal_payment_split(amt, move):
                if part[0] == "cash":
                    outcome["cash"] += part[1]
                else:
                    outcome["by_pm"][part[2]] += part[1]

        PledgeLine = self.env["pos.advance.order.pledge"].sudo()
        returned_here = PledgeLine.search([
            ("state", "=", "returned"),
            ("return_move_id.state", "=", "posted"),
            ("return_move_id.create_date", ">=", self.start_at),
            ("return_move_id.create_date", "<=", end),
            ("pos_order_id", "!=", False),
        ])
        seen_orders = set()
        for pl in returned_here:
            order = pl.pos_order_id
            if not order or order.id in seen_orders:
                continue
            if order.session_id.id == self.id:
                continue
            seen_orders.add(order.id)
            move = order.sudo().pledge_deposit_move_id
            if not move or move.state != "posted":
                continue
            amt = order.total_pledge_amount or 0.0
            for part in self._iter_pledge_journal_payment_split(amt, move):
                if part[0] == "cash":
                    outcome["cash"] -= part[1]
                else:
                    outcome["by_pm"][part[2]] -= part[1]

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
        'order_ids.advance_pledge_line_ids.state',
        'order_ids.advance_pledge_line_ids.return_move_id.state',
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
