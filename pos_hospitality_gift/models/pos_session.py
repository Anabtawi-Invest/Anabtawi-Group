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
        if not stock_expense:
            return

        company = self.company_id
        hospitality_account = company.gift_expense_account_id
        if not hospitality_account:
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s skip gift cost reroute: missing hospitality expense account",
                self.name,
            )
            return

        amount_precision = company.currency_id.rounding
        gift_amount_by_source_account = defaultdict(float)
        closed_orders = self._get_closed_orders().filtered(
            lambda order: not order.is_invoiced and not order.shipping_date
        )
        gift_lines = closed_orders.mapped("lines").filtered(
            lambda line: line.is_gift
            and line.product_id.is_storable
            and line.product_id.valuation == "real_time"
        )

        for line in gift_lines:
            source_account = line.product_id._get_product_accounts().get("expense")
            if not source_account:
                continue
            if source_account == hospitality_account:
                continue

            line_cost_company_currency = self._get_gift_line_cost_company_currency(line)
            if float_is_zero(
                line_cost_company_currency, precision_rounding=amount_precision
            ):
                continue
            gift_amount_by_source_account[source_account] += line_cost_company_currency

        if not gift_amount_by_source_account:
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s skip gift cost reroute: no eligible non-zero gift cost found",
                self.name,
            )
            return

        for source_account, amount in gift_amount_by_source_account.items():
            if float_is_zero(amount, precision_rounding=amount_precision):
                continue

            stock_expense[source_account] = self._update_amounts(
                stock_expense[source_account],
                {"amount": -amount},
                self.stop_at,
                force_company_currency=True,
            )
            stock_expense[hospitality_account] = self._update_amounts(
                stock_expense[hospitality_account],
                {"amount": amount},
                self.stop_at,
                force_company_currency=True,
            )
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s gift cost rerouted: source_account=%s hospitality_account=%s amount=%s",
                self.name,
                source_account.display_name,
                hospitality_account.display_name,
                amount,
            )

    def _get_gift_line_cost_company_currency(self, line):
        company_currency = line.company_id.currency_id
        amount_precision = company_currency.rounding
        order_date = line.order_id.date_order
        line_cost = line.total_cost
        if not float_is_zero(line_cost, precision_rounding=amount_precision):
            return line.currency_id._convert(
                line_cost,
                company_currency,
                line.company_id,
                order_date,
            )

        fallback_cost = line.qty * line.product_id.standard_price
        cost_currency = line.product_id.sudo().cost_currency_id
        if float_is_zero(fallback_cost, precision_rounding=amount_precision):
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s gift line %s skipped: total_cost is zero and fallback qty*standard_price is zero",
                self.name,
                line.id,
            )
            return 0.0

        converted_fallback = cost_currency._convert(
            fallback_cost,
            company_currency,
            line.company_id,
            order_date,
        )
        _logger.warning(
            "[POS_HOSPITALITY_GIFT] Session %s gift line %s fallback cost used: qty=%s standard_price=%s fallback_company_currency=%s",
            self.name,
            line.id,
            line.qty,
            line.product_id.standard_price,
            converted_fallback,
        )
        return converted_fallback
