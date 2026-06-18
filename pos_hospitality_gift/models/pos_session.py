import logging
from collections import defaultdict

from odoo import _, models
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    def _create_non_reconciliable_move_lines(self, data):
        data = super()._create_non_reconciliable_move_lines(data)
        self._create_gift_stock_expense_reclass_lines(data)
        return data

    def _create_gift_stock_expense_reclass_lines(self, data):
        self.ensure_one()
        move_line_model = data.get("MoveLine")
        if not move_line_model:
            return
        company = self.company_id
        expense_account = company.gift_expense_account_id
        if not expense_account:
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s skip gift stock reclass: missing hospitality expense account",
                self.name,
            )
            return

        amount_precision = company.currency_id.rounding
        amounts_by_source = defaultdict(float)
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
            if not source_account or source_account == expense_account:
                continue
            if float_is_zero(line.total_cost, precision_rounding=amount_precision):
                continue
            amounts_by_source[source_account] += line.total_cost

        if not amounts_by_source:
            return

        line_vals = []
        for source_account, amount in amounts_by_source.items():
            if float_is_zero(amount, precision_rounding=amount_precision):
                continue
            amount_abs = abs(amount)
            description = _("Gift stock expense reclass")
            if amount > 0:
                line_vals.append(
                    self._debit_amounts(
                        {
                            "name": description,
                            "account_id": expense_account.id,
                            "move_id": self.move_id.id,
                        },
                        amount_abs,
                        amount_abs,
                        force_company_currency=True,
                    )
                )
                line_vals.append(
                    self._credit_amounts(
                        {
                            "name": description,
                            "account_id": source_account.id,
                            "move_id": self.move_id.id,
                        },
                        amount_abs,
                        amount_abs,
                        force_company_currency=True,
                    )
                )
            else:
                line_vals.append(
                    self._debit_amounts(
                        {
                            "name": description,
                            "account_id": source_account.id,
                            "move_id": self.move_id.id,
                        },
                        amount_abs,
                        amount_abs,
                        force_company_currency=True,
                    )
                )
                line_vals.append(
                    self._credit_amounts(
                        {
                            "name": description,
                            "account_id": expense_account.id,
                            "move_id": self.move_id.id,
                        },
                        amount_abs,
                        amount_abs,
                        force_company_currency=True,
                    )
                )

        if line_vals:
            move_line_model.create(line_vals)
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s gift stock reclass posted for %s source account(s)",
                self.name,
                len(amounts_by_source),
            )
