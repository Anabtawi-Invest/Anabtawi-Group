# -*- coding: utf-8 -*-
from collections import defaultdict
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


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
            extra_cash = deposited_summary.get("cash") or 0.0
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

    def _advance_orders_deposited_in_session(self):
        """Advance orders whose deposit was collected during this POS session."""
        self.ensure_one()
        AdvanceOrder = self.env["pos.advance.order"].sudo()
        has_session_col = AdvanceOrder._deposit_session_column_exists()
        if not has_session_col:
            _logger.warning(
                "[ADV_CLOSING] deposit_pos_session_id column missing on %s; "
                "upgrade pos_advance_order. Falling back to deposit move date matching.",
                self.name,
            )
            return self._advance_orders_deposited_in_session_legacy_sql(AdvanceOrder)
        base_domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "not in", ("draft", "cancel")),
            ("advance_deposit_move_id.state", "=", "posted"),
        ]
        end = self.stop_at or fields.Datetime.now()
        deposited = AdvanceOrder.browse()
        for adv_order in AdvanceOrder.search(base_domain):
            if adv_order.deposit_pos_session_id == self:
                deposited |= adv_order
                continue
            pay_cfg = adv_order.from_pos_config_id or adv_order.pos_config_id
            if pay_cfg != self.config_id:
                continue
            move = adv_order.advance_deposit_move_id
            if not move:
                continue
            if not self.start_at:
                continue
            if not (self.start_at <= move.create_date <= end):
                continue
            if adv_order.deposit_pos_session_id and adv_order.deposit_pos_session_id != self:
                continue
            deposited |= adv_order
        _logger.info(
            "[ADV_CLOSING] session=%s(%s) deposited_advances=%s",
            self.name,
            self.id,
            deposited.mapped("name"),
        )
        return deposited

    def _advance_orders_deposited_in_session_legacy_sql(self, AdvanceOrder):
        """Match deposits by From POS + move date when DB column is not upgraded yet."""
        self.ensure_one()
        if not self.start_at:
            return AdvanceOrder.browse()
        end = self.stop_at or fields.Datetime.now()
        self.env.cr.execute(
            """
            SELECT ao.id
              FROM pos_advance_order ao
              JOIN account_move am ON am.id = ao.advance_deposit_move_id
             WHERE ao.company_id = %s
               AND ao.state NOT IN ('draft', 'cancel')
               AND am.state = 'posted'
               AND COALESCE(ao.from_pos_config_id, ao.pos_config_id) = %s
               AND am.create_date >= %s
               AND am.create_date <= %s
            """,
            (self.company_id.id, self.config_id.id, self.start_at, end),
        )
        ids = [row[0] for row in self.env.cr.fetchall()]
        deposited = AdvanceOrder.browse(ids)
        _logger.info(
            "[ADV_CLOSING] session=%s(%s) legacy_sql_deposited=%s",
            self.name,
            self.id,
            deposited.mapped("name"),
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
        if not self.config_id.enable_advance_order:
            return summary
        AdvanceOrder = self.env["pos.advance.order"].sudo()
        deposited = self._advance_orders_deposited_in_session()
        if not deposited:
            return summary
        currency = self.currency_id
        cash_total = 0.0
        bank_total = 0.0
        cash_count = 0
        bank_count = 0
        read_fields = ["advance_amount", "pos_payment_method_id", "payment_method"]
        if AdvanceOrder._deposit_session_column_exists():
            adv_rows = deposited
        else:
            adv_rows = deposited.read(read_fields)
        for adv_order in adv_rows:
            if isinstance(adv_order, dict):
                amount = adv_order.get("advance_amount") or 0.0
                pm_id = (adv_order.get("pos_payment_method_id") or [False])[0]
                pm = self.env["pos.payment.method"].browse(pm_id) if pm_id else self.env["pos.payment.method"]
                payment_method = adv_order.get("payment_method")
            else:
                amount = adv_order.advance_amount or 0.0
                pm = adv_order.pos_payment_method_id
                payment_method = adv_order.payment_method
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
        return summary

    def get_closing_control_data(self):
        """Keep reclassification logic and only change advance presentation in closing UI."""
        data = super().get_closing_control_data()
        self.ensure_one()
        cfg = self.config_id
        if not cfg.enable_advance_order:
            return data

        deposited_summary = self._get_deposited_advance_summary()
        deposit_cash = deposited_summary["cash"]
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
        reclassified_advance_by_pm = defaultdict(lambda: {"amount": 0.0, "number": 0})
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
            default_cash["advance_applied_amount"] = 0.0
            default_cash["advance_payment_amount"] = 0.0
        for row in non_cash:
            row["advance_deposit_amount"] = 0.0
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

        non_cash = [
            row
            for row in non_cash
            if (
                not float_is_zero(row.get("amount") or 0.0, precision_rounding=rounding)
                or not float_is_zero(row.get("advance_deposit_amount") or 0.0, precision_rounding=rounding)
            )
        ]

        deposit_bank = deposited_summary["bank"]
        deposit_total = self.currency_id.round(deposit_cash + deposit_bank)
        deposit_count = (deposited_summary.get("cash_count") or 0) + (
            deposited_summary.get("bank_count") or 0
        )
        data["advance_deposit_details"] = {
            "cash_amount": deposit_cash,
            "bank_amount": deposit_bank,
            "total_amount": deposit_total,
            "count": deposit_count,
        }

        data["default_cash_details"] = default_cash or data.get("default_cash_details")
        data["non_cash_payment_methods"] = non_cash
        _logger.info(
            "[ADV_CLOSING] session=%s(%s) default_cash=%s non_cash_rows=%s advance_deposit_details=%s",
            self.name,
            self.id,
            data.get("default_cash_details"),
            data.get("non_cash_payment_methods"),
            data.get("advance_deposit_details"),
        )
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
            # Reroute only the advance-application payment line on completion order.
            # Keep normal customer cash/bank payments on standard POS receivable flow.
            if not advance.remaining_pos_order_id or order.id != advance.remaining_pos_order_id.id:
                return super()._get_split_receivable_vals(
                    payment, amount, amount_converted
                )
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
        """Session move lines created for prepaid advance (pay_later) on completion orders."""
        self.ensure_one()
        advance_lines = self.env["account.move.line"]
        rounding = self.currency_id.rounding

        for order in self._get_closed_orders():
            advance = order.advance_order_id
            if not advance or not advance.remaining_pos_order_id:
                continue
            if order.id != advance.remaining_pos_order_id.id:
                continue
            receivable_account = advance._get_advance_receivable_account()
            if not receivable_account:
                continue
            try:
                advance_application_pm = advance._get_advance_application_payment_method(self)
            except UserError:
                continue

            for payment in order.payment_ids.filtered(
                lambda pay: pay.payment_method_id == advance_application_pm
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
                        ) == 0
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

        payment_domain = lambda pay: pay.amount > 0
        if match_advance_application_pm and advance_application_pm:
            payment_domain = lambda pay: (
                pay.amount > 0 and pay.payment_method_id == advance_application_pm
            )
        advance_payment = pos_order.payment_ids.filtered(payment_domain)[:1]

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
