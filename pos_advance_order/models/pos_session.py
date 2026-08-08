# -*- coding: utf-8 -*-
from collections import defaultdict
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)

_ADV_DEPOSIT_MSG_RE = re.compile(r"ADV_DEPOSIT:(\d+)")
_ADV_REFUND_MSG_RE = re.compile(r"ADV_REFUND:(\d+):(\d+):([\d.]+)")
_ADV_SAME_SESSION_APPLY_RE = re.compile(r"ADV_SAME_SESSION_APPLY:(\d+):(\d+)")


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.depends(
        "payment_method_ids",
        "order_ids",
        "cash_register_balance_start",
        "cash_register_balance_end_real",
        "statement_line_ids.amount",
    )
    def _compute_cash_balance(self):
        """Include deposited cash advances in theoretical drawer cash."""
        super()._compute_cash_balance()
        for session in self:
            if not session.config_id.enable_advance_order:
                continue
            deposited_summary = session._get_deposited_advance_summary()
            refunded_summary = session._get_refunded_advance_summary()
            same_session_apply_ids = session._get_same_session_apply_payment_ids()
            same_session_cash_apply = 0.0
            if same_session_apply_ids:
                for pay in (
                    session.env["pos.payment"]
                    .sudo()
                    .browse(list(same_session_apply_ids))
                    .exists()
                ):
                    if pay.payment_method_id.type == "cash":
                        same_session_cash_apply += pay.amount or 0.0
            extra_cash = session.currency_id.round(
                (deposited_summary.get("cash") or 0.0)
                - (refunded_summary.get("cash") or 0.0)
                - same_session_cash_apply
            )
            if session.currency_id.is_zero(extra_cash):
                continue
            before_end = session.cash_register_balance_end or 0.0
            before_diff = session.cash_register_difference or 0.0
            session.cash_register_balance_end = session.currency_id.round(
                (session.cash_register_balance_end or 0.0) + extra_cash
            )
            session.cash_register_difference = session.currency_id.round(
                (session.cash_register_balance_end_real or 0.0) - session.cash_register_balance_end
            )
            _logger.info(
                "[ADV_CASH_BALANCE] session=%s(%s) extra_cash=%s before_end=%s after_end=%s before_diff=%s after_diff=%s",
                session.name,
                session.id,
                extra_cash,
                before_end,
                session.cash_register_balance_end,
                before_diff,
                session.cash_register_difference,
            )

    def _advance_orders_from_session_messages(self):
        """Advance orders explicitly registered on this session at deposit time."""
        self.ensure_one()
        # sudo: POS users may not read internal session notes via message_ids
        messages = self.env["mail.message"].sudo().search(
            [
                ("model", "=", "pos.session"),
                ("res_id", "=", self.id),
                ("body", "ilike", "ADV_DEPOSIT:"),
            ],
            order="id desc",
        )
        message_ids_raw = []
        advance_ids = []
        for message in messages:
            body = message.body or ""
            found = [int(adv_id) for adv_id in _ADV_DEPOSIT_MSG_RE.findall(body)]
            message_ids_raw.append(
                {"msg_id": message.id, "body": body[:200], "advance_ids": found}
            )
            advance_ids.extend(found)

        _logger.info(
            "[ADV_TRACE] session=%s(%s) message_scan count=%s parsed=%s details=%s "
            "message_ids_rel_count=%s",
            self.name,
            self.id,
            len(messages),
            advance_ids,
            message_ids_raw,
            len(self.message_ids),
        )

        if not advance_ids:
            return self.env["pos.advance.order"].browse()

        candidates = (
            self.env["pos.advance.order"]
            .sudo()
            .browse(list(set(advance_ids)))
            .exists()
        )
        deposited = self.env["pos.advance.order"].browse()
        for ao in candidates:
            reasons = []
            if ao.state == "draft":
                reasons.append("bad_state=draft")
            if not ao.advance_deposit_move_id and not ao.advance_pos_order_id:
                reasons.append("no_deposit")
            elif ao.advance_deposit_move_id:
                move_state = ao.advance_deposit_move_id.state
                # After refund the deposit move is cancelled; still count the in-session
                # receipt so net closing = deposits - refunds (ADV_REFUND markers).
                if move_state not in ("posted", "cancel"):
                    reasons.append(f"move_state={move_state}")
            if ao.company_id != self.company_id:
                _logger.warning(
                    "[ADV_TRACE] session=%s accepting message-linked advance=%s(%s) "
                    "despite company_mismatch ao=%s session=%s",
                    self.id,
                    ao.name,
                    ao.id,
                    ao.company_id.id,
                    self.company_id.id,
                )
            if reasons:
                _logger.warning(
                    "[ADV_TRACE] session=%s rejected advance=%s(%s) reasons=%s",
                    self.id,
                    ao.name,
                    ao.id,
                    reasons,
                )
            else:
                deposited |= ao

        _logger.info(
            "[ADV_TRACE] session=%s(%s) message_deposited=%s",
            self.name,
            self.id,
            deposited.mapped("name"),
        )
        return deposited

    def _advance_orders_deposited_in_session(self):
        """Advance orders whose deposit belongs to this POS session."""
        self.ensure_one()
        AdvanceOrder = self.env["pos.advance.order"].sudo()
        from_messages = self._advance_orders_from_session_messages()
        start = self.start_at or self.create_date
        if self.start_at and self.create_date:
            start = min(self.start_at, self.create_date)
        if not start:
            return from_messages
        end = self.stop_at or fields.Datetime.now()
        session_ref_pattern = f"%[pos_session_id:{self.id}]%"
        journal_ids = self.payment_method_ids.mapped("journal_id").ids or [0]
        config_id = self.config_id.id
        self.env.cr.execute(
            """
            SELECT DISTINCT ao.id
              FROM pos_advance_order ao
              JOIN account_move am ON am.id = ao.advance_deposit_move_id
             WHERE ao.company_id = %s
               AND ao.state NOT IN ('draft', 'cancel')
               AND am.state = 'posted'
               AND (
                    am.ref LIKE %s
                    OR (
                        am.create_date >= %s
                        AND am.create_date <= %s
                        AND (
                            COALESCE(ao.from_pos_config_id, ao.pos_config_id) = %s
                            OR am.journal_id = ANY(%s)
                        )
                    )
                    OR (
                        ao.create_date >= %s
                        AND ao.create_date <= %s
                        AND COALESCE(ao.from_pos_config_id, ao.pos_config_id) = %s
                    )
               )
            """,
            (
                self.company_id.id,
                session_ref_pattern,
                start,
                end,
                config_id,
                journal_ids,
                start,
                end,
                config_id,
            ),
        )
        from_sql = AdvanceOrder.browse([row[0] for row in self.env.cr.fetchall()])
        deposited = from_messages | from_sql

        _logger.info(
            "[ADV_TRACE] session=%s(%s) deposit_lookup start=%s end=%s config=%s "
            "from_messages=%s from_sql=%s journals=%s ref_pattern=%s",
            self.name,
            self.id,
            start,
            end,
            config_id,
            from_messages.ids,
            from_sql.ids,
            journal_ids,
            session_ref_pattern,
        )

        if not deposited:
            self.env.cr.execute(
                """
                SELECT ao.id, ao.name, ao.state, ao.create_date,
                       am.id, am.create_date, am.ref
                  FROM pos_advance_order ao
                  LEFT JOIN account_move am ON am.id = ao.advance_deposit_move_id
                 WHERE ao.company_id = %s
                   AND ao.state NOT IN ('draft', 'cancel')
                 ORDER BY ao.id DESC
                 LIMIT 5
                """,
                (self.company_id.id,),
            )
            recent = self.env.cr.fetchall()
            self.env.cr.execute(
                """
                SELECT COUNT(*)
                  FROM pos_advance_order ao
                  JOIN account_move am ON am.id = ao.advance_deposit_move_id
                 WHERE ao.company_id = %s
                   AND ao.state NOT IN ('draft', 'cancel')
                   AND am.state = 'posted'
                   AND am.create_date >= %s
                   AND am.create_date <= %s
                """,
                (self.company_id.id, start, end),
            )
            window_count = self.env.cr.fetchone()[0]
            _logger.warning(
                "[ADV_TRACE] session=%s(%s) NO_DEPOSITS config=%s start=%s end=%s "
                "window_deposits=%s journals=%s ref_pattern=%s recent_advances=%s",
                self.name,
                self.id,
                config_id,
                start,
                end,
                window_count,
                journal_ids,
                session_ref_pattern,
                recent,
            )
        _logger.info(
            "[ADV_CLOSING] session=%s(%s) deposited_advances=%s ids=%s",
            self.name,
            self.id,
            deposited.mapped("name"),
            deposited.ids,
        )
        return deposited

    def _get_deposited_advance_summary(self):
        """Split deposited advances by liquidity type for closing register display."""
        self.ensure_one()
        summary = {
            "cash": 0.0,
            "bank": 0.0,
            "cash_count": 0,
            "bank_count": 0,
            "by_payment_method": {},
        }
        deposited = self._advance_orders_deposited_in_session()
        if not deposited:
            _logger.info(
                "[ADV_TRACE] session=%s(%s) summary_empty (no deposited advances)",
                self.name,
                self.id,
            )
            return summary
        currency = self.currency_id
        cash_total = 0.0
        bank_total = 0.0
        cash_count = 0
        bank_count = 0
        for row in deposited.read(["advance_amount", "pos_payment_method_id", "payment_method"]):
            amount = row.get("advance_amount") or 0.0
            pm_id = (row.get("pos_payment_method_id") or [False])[0]
            pm = self.env["pos.payment.method"].browse(pm_id) if pm_id else self.env["pos.payment.method"]
            payment_method = row.get("payment_method")
            if currency.is_zero(amount):
                continue
            is_cash = (pm and pm.type == "cash") or (not pm and payment_method == "cash")
            pm_key = pm.id if pm else False
            pm_bucket = summary["by_payment_method"].setdefault(
                pm_key,
                {
                    "amount": 0.0,
                    "count": 0,
                    "type": pm.type if pm else ("cash" if is_cash else "bank"),
                },
            )
            pm_bucket["amount"] += amount
            pm_bucket["count"] += 1
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
        for bucket in summary["by_payment_method"].values():
            bucket["amount"] = currency.round(bucket["amount"])
        _logger.info(
            "[ADV_TRACE] session=%s(%s) summary cash=%s bank=%s count=%s by_pm=%s",
            self.name,
            self.id,
            summary["cash"],
            summary["bank"],
            summary["cash_count"] + summary["bank_count"],
            summary["by_payment_method"],
        )
        return summary

    def _get_refunded_advance_summary(self):
        """Split advance refunds registered on this session by payment method (closing register)."""
        self.ensure_one()
        summary = {
            "cash": 0.0,
            "bank": 0.0,
            "cash_count": 0,
            "bank_count": 0,
            "by_payment_method": {},
        }
        messages = self.env["mail.message"].sudo().search(
            [
                ("model", "=", "pos.session"),
                ("res_id", "=", self.id),
                ("body", "ilike", "ADV_REFUND:"),
            ],
            order="id desc",
        )
        if not messages:
            return summary

        currency = self.currency_id
        cash_total = 0.0
        bank_total = 0.0
        cash_count = 0
        bank_count = 0
        seen_markers = set()
        for message in messages:
            body = message.body or ""
            for advance_id, pm_id_str, amount_str in _ADV_REFUND_MSG_RE.findall(body):
                marker = f"{advance_id}:{pm_id_str}:{amount_str}"
                if marker in seen_markers:
                    continue
                seen_markers.add(marker)
                amount = currency.round(float(amount_str))
                if currency.is_zero(amount):
                    continue
                pm_id = int(pm_id_str)
                pm = self.env["pos.payment.method"].browse(pm_id)
                is_cash = pm and pm.type == "cash"
                pm_key = pm.id if pm else False
                pm_bucket = summary["by_payment_method"].setdefault(
                    pm_key,
                    {
                        "amount": 0.0,
                        "count": 0,
                        "type": pm.type if pm else "bank",
                    },
                )
                pm_bucket["amount"] += amount
                pm_bucket["count"] += 1
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
        for bucket in summary["by_payment_method"].values():
            bucket["amount"] = currency.round(bucket["amount"])
        _logger.info(
            "[ADV_TRACE] session=%s(%s) refund_summary cash=%s bank=%s count=%s by_pm=%s",
            self.name,
            self.id,
            summary["cash"],
            summary["bank"],
            summary["cash_count"] + summary["bank_count"],
            summary["by_payment_method"],
        )
        return summary

    def _get_same_session_apply_payment_ids(self):
        """pos.payment ids flagged as prepaid advance on this session (not pay_later)."""
        self.ensure_one()
        messages = self.env["mail.message"].sudo().search(
            [
                ("model", "=", "pos.session"),
                ("res_id", "=", self.id),
                ("body", "ilike", "ADV_SAME_SESSION_APPLY:"),
            ]
        )
        payment_ids = set()
        for message in messages:
            body = message.body or ""
            for _advance_id, payment_id in _ADV_SAME_SESSION_APPLY_RE.findall(body):
                payment_ids.add(int(payment_id))

        if not payment_ids and self.config_id.enable_advance_order:
            payment_ids = self._fallback_same_session_apply_payment_ids()

        if payment_ids:
            _logger.info(
                "[ADV_TRACE] session=%s(%s) same_session_apply_payments=%s",
                self.name,
                self.id,
                sorted(payment_ids),
            )
        return payment_ids

    def _fallback_same_session_apply_payment_ids(self):
        """Detect same-session advance application payments when session markers are missing."""
        self.ensure_one()
        payment_ids = set()
        rounding = self.currency_id.rounding
        deposited_advances = self._advance_orders_from_session_messages()

        for order in self._get_closed_orders():
            advance = order.advance_order_id
            if not advance or advance not in deposited_advances:
                continue
            remaining = advance.remaining_pos_order_id
            if not remaining or order.id != remaining.id:
                continue
            deposit_pm = advance.pos_payment_method_id
            advance_part = advance.advance_amount or 0.0
            if not deposit_pm or float_is_zero(advance_part, precision_rounding=rounding):
                continue
            candidates = order.payment_ids.filtered(
                lambda pay: (
                    pay.amount > 0.0
                    and pay.payment_method_id == deposit_pm
                    and float_compare(
                        pay.amount, advance_part, precision_rounding=rounding
                    )
                    == 0
                )
            )
            if len(candidates) == 1:
                payment_ids.add(candidates.id)
            elif len(candidates) > 1:
                _logger.warning(
                    "[ADV_TRACE] session=%s(%s) ambiguous same_session_apply advance=%s candidates=%s",
                    self.name,
                    self.id,
                    advance.name,
                    candidates.ids,
                )
        return payment_ids

    def get_closing_control_data(self):
        """Keep reclassification logic and only change advance presentation in closing UI."""
        self.ensure_one()
        _logger.info(
            "[ADV_TRACE] get_closing_control_data START session=%s(%s) state=%s config=%s "
            "enable_advance_order=%s start_at=%s user=%s",
            self.name,
            self.id,
            self.state,
            self.config_id.id,
            self.config_id.enable_advance_order,
            self.start_at,
            self.env.user.login,
        )
        data = super().get_closing_control_data()
        cfg = self.config_id

        deposited_summary = self._get_deposited_advance_summary()
        refunded_summary = self._get_refunded_advance_summary()
        deposit_cash = deposited_summary["cash"]
        deposit_bank = deposited_summary["bank"]
        refund_cash = refunded_summary["cash"]
        refund_bank = refunded_summary["bank"]
        deposit_total = self.currency_id.round(deposit_cash + deposit_bank)
        refund_total = self.currency_id.round(refund_cash + refund_bank)
        has_deposits = not float_is_zero(
            deposit_total, precision_rounding=self.currency_id.rounding
        )
        has_refunds = not float_is_zero(
            refund_total, precision_rounding=self.currency_id.rounding
        )
        _logger.info(
            "[ADV_TRACE] session=%s(%s) has_deposits=%s deposit_total=%s cash=%s bank=%s "
            "has_refunds=%s refund_total=%s refund_cash=%s refund_bank=%s",
            self.name,
            self.id,
            has_deposits,
            deposit_total,
            deposit_cash,
            deposit_bank,
            has_refunds,
            refund_total,
            refund_cash,
            refund_bank,
        )
        if not cfg.enable_advance_order and not has_deposits and not has_refunds:
            _logger.info(
                "[ADV_TRACE] session=%s(%s) SKIP advance UI (enable_advance_order=False, no deposits)",
                self.name,
                self.id,
            )
            return data

        deposited_by_pm = deposited_summary.get("by_payment_method", {})
        _logger.info(
            "[ADV_CLOSING] session=%s(%s) deposit_cash=%s deposited_by_pm=%s",
            self.name,
            self.id,
            deposit_cash,
            deposited_by_pm,
        )

        rounding = self.currency_id.rounding
        orders = self._get_closed_orders()
        same_session_apply_ids = self._get_same_session_apply_payment_ids()
        reclassified_advance_by_pm = defaultdict(lambda: {"amount": 0.0, "number": 0})
        for order in orders:
            advance = order.advance_order_id
            if not advance or not advance.pos_config_id:
                continue
            remaining = advance.remaining_pos_order_id
            if not remaining or order.id != remaining.id:
                continue
            for pay in order.payment_ids:
                if pay.amount <= 0.0:
                    continue
                if pay.id in same_session_apply_ids:
                    advance_part = min(advance.advance_amount or 0.0, pay.amount)
                    if float_is_zero(advance_part, precision_rounding=rounding):
                        continue
                    bucket = reclassified_advance_by_pm[pay.payment_method_id.id]
                    bucket["amount"] += advance_part
                    bucket["number"] += 1
            if any(pay.id in same_session_apply_ids for pay in order.payment_ids):
                continue
            try:
                app_pm = advance._get_advance_application_payment_method(self)
            except UserError:
                continue
            positive_amount_on_method = sum(
                pay.amount
                for pay in order.payment_ids
                if pay.payment_method_id == app_pm
                and pay.amount > 0.0
            )
            advance_part = min(advance.advance_amount or 0.0, positive_amount_on_method)
            if float_is_zero(advance_part, precision_rounding=rounding):
                continue
            bucket = reclassified_advance_by_pm[app_pm.id]
            bucket["amount"] += advance_part
            bucket["number"] += 1

        default_cash = data.get("default_cash_details") or {}
        dc_id = default_cash.get("id")
        non_cash = list(data.get("non_cash_payment_methods") or [])
        if default_cash:
            default_cash["advance_deposit_amount"] = 0.0
            default_cash["advance_refund_amount"] = 0.0
            default_cash["advance_applied_amount"] = 0.0
            default_cash["advance_payment_amount"] = 0.0
        for row in non_cash:
            row["advance_deposit_amount"] = 0.0
            row["advance_refund_amount"] = 0.0
            row["advance_applied_amount"] = 0.0
            row["advance_payment_amount"] = 0.0

        for pm_id, payload in reclassified_advance_by_pm.items():
            amt = self.currency_id.round(payload["amount"])
            if float_is_zero(amt, precision_rounding=rounding):
                continue
            if dc_id and pm_id == dc_id:
                default_cash["advance_applied_amount"] = self.currency_id.round(
                    (default_cash.get("advance_applied_amount") or 0.0) + amt
                )
                default_cash["amount"] = self.currency_id.round(
                    (default_cash.get("amount") or 0.0) - amt
                )
                default_cash["payment_amount"] = self.currency_id.round(
                    (default_cash.get("payment_amount") or 0.0) - amt
                )
                continue
            for row in non_cash:
                if row.get("id") == pm_id:
                    row["amount"] = self.currency_id.round(row["amount"] - amt)
                    row["number"] = max(0, (row.get("number") or 0) - payload["number"])
                    row["advance_applied_amount"] = self.currency_id.round(
                        (row.get("advance_applied_amount") or 0.0) + amt
                    )
                    break
        _logger.info(
            "[ADV_CLOSING] session=%s(%s) reclassified_by_pm=%s",
            self.name,
            self.id,
            {pm_id: self.currency_id.round(v["amount"]) for pm_id, v in reclassified_advance_by_pm.items()},
        )

        if default_cash and not float_is_zero(deposit_cash, precision_rounding=rounding):
            default_cash["advance_deposit_amount"] = self.currency_id.round(deposit_cash)
            default_cash["advance_payment_amount"] = default_cash["advance_deposit_amount"]
            default_cash["amount"] = self.currency_id.round(
                (default_cash.get("amount") or 0.0) + deposit_cash
            )
            default_cash["payment_amount"] = self.currency_id.round(
                (default_cash.get("payment_amount") or 0.0) + deposit_cash
            )

        non_cash_by_id = {row.get("id"): row for row in non_cash}
        bank_fallback_row = next((row for row in non_cash if row.get("type") == "bank"), None)

        for pm_id, bucket in deposited_by_pm.items():
            deposit_amount = self.currency_id.round(bucket.get("amount") or 0.0)
            if float_is_zero(deposit_amount, precision_rounding=rounding):
                continue
            if bucket.get("type") == "cash":
                continue

            target_row = None
            if pm_id and pm_id in non_cash_by_id:
                target_row = non_cash_by_id[pm_id]
            else:
                target_row = bank_fallback_row

            if not target_row:
                continue

            target_row["advance_deposit_amount"] = self.currency_id.round(
                (target_row.get("advance_deposit_amount") or 0.0) + deposit_amount
            )
            target_row["advance_payment_amount"] = target_row["advance_deposit_amount"]
            target_row["amount"] = self.currency_id.round(
                (target_row.get("amount") or 0.0) + deposit_amount
            )
            target_row["payment_amount"] = self.currency_id.round(
                (target_row.get("payment_amount") or 0.0) + deposit_amount
            )

        refunded_by_pm = refunded_summary.get("by_payment_method", {})
        if default_cash and not float_is_zero(refund_cash, precision_rounding=rounding):
            default_cash["advance_refund_amount"] = self.currency_id.round(refund_cash)
            default_cash["amount"] = self.currency_id.round(
                (default_cash.get("amount") or 0.0) - refund_cash
            )
            default_cash["payment_amount"] = self.currency_id.round(
                (default_cash.get("payment_amount") or 0.0) - refund_cash
            )

        for pm_id, bucket in refunded_by_pm.items():
            refund_amount = self.currency_id.round(bucket.get("amount") or 0.0)
            if float_is_zero(refund_amount, precision_rounding=rounding):
                continue
            if bucket.get("type") == "cash":
                continue

            target_row = None
            if pm_id and pm_id in non_cash_by_id:
                target_row = non_cash_by_id[pm_id]
            else:
                target_row = bank_fallback_row

            if not target_row:
                continue

            target_row["advance_refund_amount"] = self.currency_id.round(
                (target_row.get("advance_refund_amount") or 0.0) + refund_amount
            )
            target_row["amount"] = self.currency_id.round(
                (target_row.get("amount") or 0.0) - refund_amount
            )
            target_row["payment_amount"] = self.currency_id.round(
                (target_row.get("payment_amount") or 0.0) - refund_amount
            )

        non_cash = [
            row
            for row in non_cash
            if (
                not float_is_zero(row.get("amount") or 0.0, precision_rounding=rounding)
                or not float_is_zero(row.get("advance_deposit_amount") or 0.0, precision_rounding=rounding)
                or not float_is_zero(row.get("advance_refund_amount") or 0.0, precision_rounding=rounding)
            )
        ]

        deposit_count = (deposited_summary.get("cash_count") or 0) + (
            deposited_summary.get("bank_count") or 0
        )
        refund_count = (refunded_summary.get("cash_count") or 0) + (
            refunded_summary.get("bank_count") or 0
        )
        data["advance_deposit_details"] = {
            "cash_amount": deposit_cash,
            "bank_amount": deposit_bank,
            "total_amount": deposit_total,
            "count": deposit_count,
        }
        data["advance_refund_details"] = {
            "cash_amount": refund_cash,
            "bank_amount": refund_bank,
            "total_amount": refund_total,
            "count": refund_count,
        }

        data["default_cash_details"] = default_cash or data.get("default_cash_details")
        data["non_cash_payment_methods"] = non_cash
        _logger.info(
            "[ADV_CLOSING] session=%s(%s) default_cash=%s non_cash_rows=%s advance_deposit_details=%s advance_refund_details=%s",
            self.name,
            self.id,
            data.get("default_cash_details"),
            data.get("non_cash_payment_methods"),
            data.get("advance_deposit_details"),
            data.get("advance_refund_details"),
        )
        return data

    def _accumulate_amounts(self, data):
        data = super()._accumulate_amounts(data)
        combine = data.get("combine_receivables_pay_later")
        if combine:
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
        else:
            data["combine_receivables_pay_later_advance"] = {}

        data = self._accumulate_same_session_advance_application_amounts(data)
        return data

    def _accumulate_same_session_advance_application_amounts(self, data):
        """Move prepaid advance payment lines off cash/bank buckets (same session as deposit)."""
        self.ensure_one()
        apply_payment_ids = self._get_same_session_apply_payment_ids()
        if not apply_payment_ids:
            data["combine_advance_application_receivable"] = {}
            return data

        amounts_fn = lambda: {"amount": 0.0, "amount_converted": 0.0}
        combine_advance_application = defaultdict(amounts_fn)
        rounding = self.currency_id.rounding

        combine_receivables_cash = data.get("combine_receivables_cash")
        combine_receivables_bank = data.get("combine_receivables_bank")
        payments = self.env["pos.payment"].sudo().browse(list(apply_payment_ids)).exists()

        for payment in payments:
            amount = payment.amount
            if float_is_zero(amount, precision_rounding=rounding):
                continue
            payment_method = payment.payment_method_id
            if payment_method.split_transactions:
                # Split cash/bank: exclude from statement in _create_cash_statement_lines.
                continue
            date = payment.payment_date
            if payment_method.type == "cash" and combine_receivables_cash is not None:
                combine_receivables_cash[payment_method] = self._update_amounts(
                    combine_receivables_cash[payment_method],
                    {"amount": -amount},
                    date,
                )
            elif payment_method.type == "bank" and combine_receivables_bank is not None:
                combine_receivables_bank[payment_method] = self._update_amounts(
                    combine_receivables_bank[payment_method],
                    {"amount": -amount},
                    date,
                )
            combine_advance_application[payment_method] = self._update_amounts(
                combine_advance_application[payment_method],
                {"amount": amount},
                date,
            )

        data["combine_advance_application_receivable"] = dict(combine_advance_application)
        _logger.info(
            "[ADV_TRACE] session=%s(%s) same_session_advance_application=%s",
            self.name,
            self.id,
            {
                pm.id: self.currency_id.round(vals["amount"])
                for pm, vals in combine_advance_application.items()
            },
        )
        return data

    def _create_cash_statement_lines_and_cash_move_lines(self, data):
        apply_payment_ids = self._get_same_session_apply_payment_ids()
        split_advance_cash = {}
        if apply_payment_ids:
            split_receivables_cash = data.get("split_receivables_cash") or {}
            for payment in list(split_receivables_cash.keys()):
                if payment.id in apply_payment_ids:
                    split_advance_cash[payment] = split_receivables_cash.pop(payment)
            data["split_receivables_cash"] = split_receivables_cash

        data = super()._create_cash_statement_lines_and_cash_move_lines(data)

        if split_advance_cash:
            MoveLine = data.get("MoveLine")
            advance_receivable_vals = [
                self._get_split_receivable_vals(
                    payment, amounts["amount"], amounts["amount_converted"]
                )
                for payment, amounts in split_advance_cash.items()
            ]
            if advance_receivable_vals:
                extra_lines = MoveLine.create(advance_receivable_vals)
                data["split_cash_receivable_lines"] = (
                    data.get("split_cash_receivable_lines") | extra_lines
                )
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
        combine_advance_application = data.get("combine_advance_application_receivable") or {}
        for payment_method, amounts in combine_advance_application.items():
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
            # Reroute only the advance-application payment line on completion order.
            # Keep normal customer cash/bank payments on standard POS receivable flow.
            if not advance.remaining_pos_order_id or order.id != advance.remaining_pos_order_id.id:
                return super()._get_split_receivable_vals(
                    payment, amount, amount_converted
                )
            same_session_apply_ids = self._get_same_session_apply_payment_ids()
            if payment.id in same_session_apply_ids:
                acc = advance.pos_config_id.pos_advance_receivable_account_id
                partial_vals = {
                    "account_id": acc.id,
                    "move_id": self.move_id.id,
                    "name": "%s - %s (Advance prepaid)" % (self.name, payment.payment_method_id.name),
                }
                return self._debit_amounts(partial_vals, amount, amount_converted)
            try:
                advance_application_pm = advance._get_advance_application_payment_method(self)
            except UserError:
                return super()._get_split_receivable_vals(
                    payment, amount, amount_converted
                )
            if payment.payment_method_id != advance_application_pm:
                return super()._get_split_receivable_vals(
                    payment, amount, amount_converted
                )
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

    def _reconcile_account_move_lines(self, data):
        data = self._split_advance_application_pay_later_lines(data)
        data = super()._reconcile_account_move_lines(data)
        if self.config_id.enable_advance_order:
            self._reconcile_advance_completion_settlements(data)
        return data

    def _split_advance_application_pay_later_lines(self, data):
        """Keep advance pay_later debits out of pos_settle_due reconciliation."""
        if not self.config_id.enable_advance_order:
            return data
        pay_later_lines = data.get("pay_later_move_lines")
        if not pay_later_lines:
            return data

        advance_lines = self._get_advance_application_pay_later_lines(pay_later_lines)
        if not advance_lines:
            return data

        data = dict(data)
        data["pay_later_move_lines"] = pay_later_lines - advance_lines
        data["advance_application_pay_later_lines"] = advance_lines
        _logger.info(
            "[ADV_SETTLEMENT_RECON] Excluded %s advance pay_later line(s) from settle_due: %s",
            len(advance_lines),
            advance_lines.ids,
        )
        return data

    def _get_advance_application_pay_later_lines(self, pay_later_lines):
        """Session move lines created for prepaid advance on completion orders."""
        self.ensure_one()
        advance_lines = self.env["account.move.line"]
        rounding = self.currency_id.rounding
        same_session_apply_ids = self._get_same_session_apply_payment_ids()

        for order in self._get_closed_orders():
            advance = order.advance_order_id
            if not advance or not advance.remaining_pos_order_id:
                continue
            if order.id != advance.remaining_pos_order_id.id:
                continue
            receivable_account = advance._get_advance_receivable_account()
            if not receivable_account:
                continue

            for payment in order.payment_ids.filtered(
                lambda pay: pay.id in same_session_apply_ids
                and not float_is_zero(pay.amount, precision_rounding=rounding)
            ):
                payment_lines = pay_later_lines.filtered(
                    lambda line: (
                        line.account_id == receivable_account
                        and line.balance > 0
                        and float_compare(
                            line.balance, payment.amount, precision_rounding=rounding
                        )
                        == 0
                    )
                )
                advance_lines |= payment_lines

            try:
                advance_application_pm = advance._get_advance_application_payment_method(self)
            except UserError:
                continue

            for payment in order.payment_ids.filtered(
                lambda pay: pay.payment_method_id == advance_application_pm
                and pay.id not in same_session_apply_ids
                and not float_is_zero(pay.amount, precision_rounding=rounding)
            ):
                accounting_partner = self.env["res.partner"]._find_accounting_partner(
                    payment.partner_id
                )
                payment_lines = pay_later_lines.filtered(
                    lambda line: (
                        line.account_id == receivable_account
                        and line.balance > 0
                        and float_compare(
                            line.balance, payment.amount, precision_rounding=rounding
                        )
                        == 0
                        and (
                            not accounting_partner
                            or line.partner_id == accounting_partner
                        )
                    )
                )
                advance_lines |= payment_lines
        return advance_lines

    def _reconcile_advance_completion_settlements(self, data):
        """Match settlement receivable credits with POS pay_later debits after session close."""
        self.ensure_one()
        if not self.move_id:
            return

        rounding = self.currency_id.rounding

        for order in self._get_closed_orders():
            advance = order.advance_order_id
            if not advance or not advance.remaining_pos_order_id:
                continue
            if order.id != advance.remaining_pos_order_id.id:
                continue

            for settlement_move, amount, settlement_order in (
                (advance.advance_completion_settlement_move_id, advance.advance_amount, order),
                (
                    advance.pledge_completion_settlement_move_id,
                    advance.pledge_amount,
                    advance.pledge_pos_order_id,
                ),
            ):
                if not settlement_move or not settlement_order:
                    continue
                if settlement_order.session_id != self:
                    continue
                self._reconcile_advance_settlement_move(
                    advance,
                    settlement_order,
                    settlement_move,
                    amount,
                    rounding,
                    data,
                    match_advance_application_pm=(
                        settlement_move == advance.advance_completion_settlement_move_id
                    ),
                )

    def _reconcile_advance_settlement_move(
        self,
        advance,
        pos_order,
        settlement_move,
        amount,
        rounding,
        data,
        match_advance_application_pm=True,
    ):
        if float_is_zero(amount, precision_rounding=rounding):
            return

        receivable_account = advance._get_advance_receivable_account()
        if not receivable_account or not receivable_account.reconcile:
            return

        settlement_lines = settlement_move.line_ids.filtered(
            lambda line: (
                line.account_id == receivable_account
                and not line.reconciled
                and line.balance < 0
                and float_compare(abs(line.balance), amount, precision_rounding=rounding) == 0
            )
        )
        if not settlement_lines:
            return

        accounting_partner = self.env["res.partner"]._find_accounting_partner(
            advance.partner_id
        )
        if accounting_partner:
            partner_settlement = settlement_lines.filtered(
                lambda line: (
                    not line.partner_id or line.partner_id == accounting_partner
                )
            )
            if partner_settlement:
                settlement_lines = partner_settlement

        settlement_line = settlement_lines[:1]
        if settlement_line.reconciled:
            return

        advance_pay_later_lines = data.get("advance_application_pay_later_lines")
        session_lines = self.env["account.move.line"]
        if advance_pay_later_lines:
            session_lines = advance_pay_later_lines.filtered(
                lambda line: (
                    line.account_id == receivable_account
                    and not line.reconciled
                    and line.balance > 0
                    and float_compare(line.balance, amount, precision_rounding=rounding) == 0
                )
            )

        if not session_lines:
            session_lines = self.move_id.line_ids.filtered(
                lambda line: (
                    line.account_id == receivable_account
                    and not line.reconciled
                    and line.balance > 0
                    and float_compare(line.balance, amount, precision_rounding=rounding) == 0
                )
            )

        try:
            advance_application_pm = (
                advance._get_advance_application_payment_method(self)
                if match_advance_application_pm
                else self.env["pos.payment.method"]
            )
        except UserError:
            advance_application_pm = self.env["pos.payment.method"]

        same_session_apply_ids = self._get_same_session_apply_payment_ids()
        advance_payment = pos_order.payment_ids.filtered(
            lambda pay: pay.amount > 0
            and (
                pay.id in same_session_apply_ids
                or (
                    match_advance_application_pm
                    and advance_application_pm
                    and pay.payment_method_id == advance_application_pm
                )
            )
        )[:1]

        if advance_payment and advance_payment.payment_method_id.split_transactions and accounting_partner:
            partner_lines = session_lines.filtered(
                lambda line: line.partner_id == accounting_partner
            )
            if partner_lines:
                session_lines = partner_lines
        elif accounting_partner:
            partner_lines = session_lines.filtered(
                lambda line: line.partner_id == accounting_partner
            )
            if partner_lines:
                session_lines = partner_lines

        if not session_lines:
            _logger.warning(
                "[ADV_SETTLEMENT_RECON] No session debit line: advance=%s settlement=%s amount=%s partner=%s",
                advance.name,
                settlement_move.id,
                amount,
                accounting_partner.id if accounting_partner else False,
            )
            return

        session_line = session_lines[:1]
        if not session_line or session_line.reconciled or settlement_line.reconciled:
            return

        lines_to_reconcile = session_line | settlement_line
        if float_compare(
            sum(lines_to_reconcile.mapped("balance")),
            0.0,
            precision_rounding=rounding,
        ) != 0:
            _logger.warning(
                "[ADV_SETTLEMENT_RECON] Unbalanced lines: advance=%s settlement=%s balances=%s",
                advance.name,
                settlement_move.id,
                lines_to_reconcile.mapped("balance"),
            )
            return

        try:
            lines_to_reconcile.with_context(no_cash_basis=True).reconcile()
        except UserError:
            lines_to_reconcile.invalidate_recordset(["reconciled", "full_reconcile_id"])
            if all(line.reconciled for line in lines_to_reconcile):
                _logger.info(
                    "[ADV_SETTLEMENT_RECON] Already reconciled: advance=%s settlement=%s session_line=%s",
                    advance.name,
                    settlement_move.id,
                    session_line.id,
                )
                return
            _logger.exception(
                "[ADV_SETTLEMENT_RECON] Failed: advance=%s settlement=%s session_line=%s",
                advance.name,
                settlement_move.id,
                session_line.id,
            )
            raise

        _logger.info(
            "[ADV_SETTLEMENT_RECON] Reconciled advance=%s settlement=%s session_line=%s settlement_line=%s",
            advance.name,
            settlement_move.id,
            session_line.id,
            settlement_line.id,
        )
