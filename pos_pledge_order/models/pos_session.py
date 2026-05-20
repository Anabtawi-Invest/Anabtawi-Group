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

    def _get_pledge_deposit_closing_summary(self):
        """Gross pledge cash effect from journal entries (not pos.payment), split in / out.

        - ``cash_in`` / ``by_pm_in``: pledge deposits for orders **in this session** (posted deposit JE).
        - ``cash_out`` / ``by_pm_out``: pledge **returns** whose reversal move was posted in this
          session window (cash left the drawer), for any linked POS order.
        - ``cash`` / ``by_pm``: net (in − out) for adjusting expected payment totals.
        """
        self.ensure_one()
        cur = self.currency_id
        end = self.stop_at or fields.Datetime.now()
        cash_in = 0.0
        cash_out = 0.0
        by_pm_in = defaultdict(float)
        by_pm_out = defaultdict(float)

        for order in self._get_closed_orders():
            move = order.sudo().pledge_deposit_move_id
            if not move or move.state != "posted":
                continue
            amt = order.total_pledge_amount or 0.0
            for part in self._iter_pledge_journal_payment_split(amt, move):
                if part[0] == "cash":
                    cash_in += part[1]
                else:
                    by_pm_in[part[2]] += part[1]

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
            seen_orders.add(order.id)
            move = order.sudo().pledge_deposit_move_id
            if not move or move.state != "posted":
                continue
            amt = order.total_pledge_amount or 0.0
            for part in self._iter_pledge_journal_payment_split(amt, move):
                if part[0] == "cash":
                    cash_out += part[1]
                else:
                    by_pm_out[part[2]] += part[1]

        cash_net = cur.round(cash_in - cash_out)
        by_pm_net = defaultdict(float)
        for pid in set(by_pm_in) | set(by_pm_out):
            by_pm_net[pid] = cur.round(by_pm_in[pid] - by_pm_out.get(pid, 0.0))

        return {
            "cash_in": cur.round(cash_in),
            "cash_out": cur.round(cash_out),
            "cash": cash_net,
            "by_pm_in": {k: cur.round(v) for k, v in by_pm_in.items()},
            "by_pm_out": {k: cur.round(v) for k, v in by_pm_out.items()},
            "by_pm": dict(by_pm_net),
        }

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
            dc["pledge_cash_in"] = summary["cash_in"]
            dc["pledge_cash_out"] = summary["cash_out"]
            dc["pledge_payment_amount"] = cash_extra
            if not cur.is_zero(cash_extra):
                dc["amount"] = cur.round(dc["amount"] + cash_extra)
            data["default_cash_details"] = dc

        patched = []
        for row in data.get("non_cash_payment_methods") or []:
            r = dict(row)
            pid = row["id"]
            pin = cur.round((summary.get("by_pm_in") or {}).get(pid, 0.0))
            pout = cur.round((summary.get("by_pm_out") or {}).get(pid, 0.0))
            r["pledge_pm_in"] = pin
            r["pledge_pm_out"] = pout
            net = cur.round((summary.get("by_pm") or {}).get(pid, 0.0))
            r["pledge_payment_amount"] = net
            if not cur.is_zero(net):
                r["amount"] = cur.round(r["amount"] + net)
            patched.append(r)
        data["non_cash_payment_methods"] = patched
        return data
