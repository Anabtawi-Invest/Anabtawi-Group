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
            move_line_model = self.env["account.move.line"].with_context(
                check_move_validity=False, skip_invoice_sync=True
            )
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s MoveLine missing in data, using fallback env['account.move.line']",
                self.name,
            )
        if not self.move_id:
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s skip gift stock reclass: session move_id is missing",
                self.name,
            )
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
        _logger.warning(
            "[POS_HOSPITALITY_GIFT] Session %s reclass debug: closed_orders=%s, expense_account=%s",
            self.name,
            closed_orders.mapped("name"),
            expense_account.display_name,
        )
        gift_lines = closed_orders.mapped("lines").filtered(
            lambda line: line.is_gift
            and line.product_id.is_storable
            and line.product_id.valuation == "real_time"
        )
        _logger.warning(
            "[POS_HOSPITALITY_GIFT] Session %s reclass debug: gift_lines_count=%s eligible_ids=%s",
            self.name,
            len(gift_lines),
            gift_lines.ids,
        )

        all_gift_lines = closed_orders.mapped("lines").filtered("is_gift")
        for line in all_gift_lines:
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s gift line debug: line_id=%s order=%s product=%s qty=%s discount=%s total_cost=%s standard_price=%s is_storable=%s valuation=%s",
                self.name,
                line.id,
                line.order_id.name,
                line.product_id.display_name,
                line.qty,
                line.discount,
                line.total_cost,
                line.product_id.standard_price,
                line.product_id.is_storable,
                line.product_id.valuation,
            )

        for line in gift_lines:
            source_account = line.product_id._get_product_accounts().get("expense")
            if not source_account:
                _logger.warning(
                    "[POS_HOSPITALITY_GIFT] Session %s skip line %s: source expense account not found for product %s",
                    self.name,
                    line.id,
                    line.product_id.display_name,
                )
                continue
            if source_account == expense_account:
                _logger.warning(
                    "[POS_HOSPITALITY_GIFT] Session %s skip line %s: source account already hospitality expense (%s)",
                    self.name,
                    line.id,
                    source_account.display_name,
                )
                continue
            if float_is_zero(line.total_cost, precision_rounding=amount_precision):
                _logger.warning(
                    "[POS_HOSPITALITY_GIFT] Session %s skip line %s: total_cost is zero (qty=%s, discount=%s, standard_price=%s)",
                    self.name,
                    line.id,
                    line.qty,
                    line.discount,
                    line.product_id.standard_price,
                )
                continue
            amounts_by_source[source_account] += line.total_cost
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s include line %s: source_account=%s add_total_cost=%s aggregated=%s",
                self.name,
                line.id,
                source_account.display_name,
                line.total_cost,
                amounts_by_source[source_account],
            )

        if not amounts_by_source:
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s skip reclass: no eligible non-zero gift cost found",
                self.name,
            )
            return

        line_vals = []
        for source_account, amount in amounts_by_source.items():
            if float_is_zero(amount, precision_rounding=amount_precision):
                _logger.warning(
                    "[POS_HOSPITALITY_GIFT] Session %s skip source account %s: aggregated amount is zero after rounding",
                    self.name,
                    source_account.display_name,
                )
                continue
            amount_abs = abs(amount)
            description = _("Gift stock expense reclass")
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s posting reclass pair: source_account=%s hospitality_account=%s amount=%s",
                self.name,
                source_account.display_name,
                expense_account.display_name,
                amount,
            )
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
                "[POS_HOSPITALITY_GIFT] Session %s gift stock reclass posted: lines=%s source_accounts=%s",
                self.name,
                len(line_vals),
                [account.display_name for account in amounts_by_source],
            )
