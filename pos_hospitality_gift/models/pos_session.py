import logging
from collections import defaultdict

from odoo import models
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    def _accumulate_amounts(self, data):
        data = super()._accumulate_amounts(data)
        self._reroute_gift_cost_to_hospitality_expense(data)
        return data

    def _reroute_gift_cost_to_hospitality_expense(self, data):
        self.ensure_one()
        stock_expense = data.get("stock_expense")
        stock_valuation = data.get("stock_valuation")
        if not stock_expense or not stock_valuation:
            return

        company = self.company_id
        hospitality_account = company.gift_expense_account_id
        if not hospitality_account:
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s skip gift cost reroute: missing hospitality expense account",
                self.name,
            )
            return

        label = self._get_gift_accounting_label()
        hospitality_key = (hospitality_account, label)
        amount_precision = company.currency_id.rounding
        closed_orders = self._get_closed_orders().filtered(
            lambda order: not order.is_invoiced and not order.shipping_date
        )
        gift_lines = closed_orders.mapped("lines").filtered(
            lambda line: line.is_gift
            and line.product_id.is_storable
            and line.product_id.valuation == "real_time"
        )

        if not gift_lines:
            return

        for line in gift_lines:
            source_account = line.product_id._get_product_accounts().get("expense")
            stock_account = line.product_id._get_product_accounts().get("stock_valuation")
            if not source_account:
                continue
            if not stock_account:
                continue

            base_cost = self._get_line_total_cost_company_currency(line)
            fallback_cost = 0.0
            if float_is_zero(base_cost, precision_rounding=amount_precision):
                fallback_cost = self._get_line_fallback_cost_company_currency(line)
            effective_cost = base_cost if not float_is_zero(
                base_cost, precision_rounding=amount_precision
            ) else fallback_cost

            if float_is_zero(effective_cost, precision_rounding=amount_precision):
                continue

            # Part 1: re-route the cost already posted by core POS
            if not float_is_zero(base_cost, precision_rounding=amount_precision):
                if source_account != hospitality_account:
                    stock_expense[source_account] = self._update_amounts(
                        stock_expense[source_account],
                        {"amount": -base_cost},
                        line.order_id.date_order or self.stop_at,
                        force_company_currency=True,
                    )
                stock_expense[hospitality_key] = self._update_amounts(
                    stock_expense[hospitality_key],
                    {"amount": base_cost},
                    line.order_id.date_order or self.stop_at,
                    force_company_currency=True,
                )
                stock_valuation[stock_account] = self._update_amounts(
                    stock_valuation[stock_account],
                    {"amount": -base_cost},
                    line.order_id.date_order or self.stop_at,
                    force_company_currency=True,
                )
                stock_valuation[(stock_account, label)] = self._update_amounts(
                    stock_valuation[(stock_account, label)],
                    {"amount": base_cost},
                    line.order_id.date_order or self.stop_at,
                    force_company_currency=True,
                )

            # Part 2: if base total_cost is zero, post fallback pair directly:
            # Dr Hospitality Expense / Cr Stock Valuation
            fallback_extra = effective_cost - base_cost
            if not float_is_zero(fallback_extra, precision_rounding=amount_precision):
                stock_expense[hospitality_key] = self._update_amounts(
                    stock_expense[hospitality_key],
                    {"amount": fallback_extra},
                    line.order_id.date_order or self.stop_at,
                    force_company_currency=True,
                )
                stock_valuation[(stock_account, label)] = self._update_amounts(
                    stock_valuation[(stock_account, label)],
                    {"amount": fallback_extra},
                    line.order_id.date_order or self.stop_at,
                    force_company_currency=True,
                )
                _logger.warning(
                    "[POS_HOSPITALITY_GIFT] Session %s gift line %s fallback used: amount=%s",
                    self.name,
                    line.id,
                    fallback_extra,
                )

            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s gift line %s rerouted: source=%s stock=%s hospitality=%s base_cost=%s effective_cost=%s",
                self.name,
                line.id,
                source_account.display_name,
                stock_account.display_name,
                hospitality_account.display_name,
                base_cost,
                effective_cost,
            )

    def _split_account_key_and_label(self, account_key):
        if (
            isinstance(account_key, tuple)
            and len(account_key) == 2
            and hasattr(account_key[0], "id")
        ):
            return account_key[0], account_key[1]
        return account_key, False

    def _get_stock_expense_vals(self, exp_account, amount, amount_converted):
        account, label = self._split_account_key_and_label(exp_account)
        partial_args = {"account_id": account.id, "move_id": self.move_id.id}
        if label:
            partial_args["name"] = label
        return self._debit_amounts(
            partial_args, amount, amount_converted, force_company_currency=True
        )

    def _get_stock_valuation_vals(self, stock_val_account, amount, amount_converted):
        account, label = self._split_account_key_and_label(stock_val_account)
        partial_args = {"account_id": account.id, "move_id": self.move_id.id}
        if label:
            partial_args["name"] = label
        return self._credit_amounts(
            partial_args, amount, amount_converted, force_company_currency=True
        )

    def _get_line_total_cost_company_currency(self, line):
        company_currency = line.company_id.currency_id
        order_date = line.order_id.date_order
        return line.currency_id._convert(
            line.total_cost,
            company_currency,
            line.company_id,
            order_date,
        )

    def _get_line_fallback_cost_company_currency(self, line):
        company_currency = line.company_id.currency_id
        order_date = line.order_id.date_order
        fallback_cost = line.qty * line.product_id.standard_price
        cost_currency = line.product_id.sudo().cost_currency_id
        return cost_currency._convert(
            fallback_cost,
            company_currency,
            line.company_id,
            order_date,
        )

    def _get_gift_accounting_label(self):
        branch_name = (self.company_id.name or "").strip()
        pos_name = (self.config_id.name or "").strip()
        return f"هدية من فرع ({branch_name}) {pos_name}".strip()
