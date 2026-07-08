from collections import defaultdict

from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class PosSession(models.Model):
    _inherit = "pos.session"

    def _load_pos_data_models(self, config):
        models_to_load = super()._load_pos_data_models(config)
        for model_name in ("online.campaign.aggregator", "online.discount.campaign"):
            if model_name not in models_to_load:
                models_to_load.append(model_name)
        return models_to_load

    def _get_order_aggregator_payments(self, order):
        """Return {aggregator: paid_amount} for POS payments linked to aggregators.

        This intentionally does not write on pos.order.line during POS session closing.
        The older stable module only posted move lines during close; it did not mutate
        order lines at that time. Keeping closing read-only avoids forcing the session
        into additional closing-control behavior while still allowing commission
        accounting for normal aggregator orders.
        """
        Aggregator = self.env["online.campaign.aggregator"]
        result = defaultdict(float)
        for payment in order.payment_ids:
            method = payment.payment_method_id
            if not method:
                continue
            aggregator = Aggregator.search([
                ("active", "=", True),
                ("company_id", "=", order.company_id.id),
                ("payment_method_ids", "in", method.id),
            ], limit=1)
            if aggregator:
                result[aggregator] += payment.amount
        return result

    def _get_commission_base_for_order_payment(self, order, paid_amount, aggregator):
        """Calculate commission base for non-campaign aggregator sales.

        - after_tax: commission is calculated on the aggregator-paid amount.
        - before_tax: commission is calculated on the tax-exclusive equivalent of the
          aggregator-paid amount. For mixed-payment orders, the untaxed amount is
          prorated by the aggregator payment ratio.
        """
        amount = abs(paid_amount)
        if aggregator.commission_base == "after_tax":
            return amount
        total = abs(order.amount_total) or 0.0
        untaxed = abs(order.amount_total - order.amount_tax)
        if float_is_zero(total, precision_rounding=order.currency_id.rounding):
            return untaxed
        return amount * untaxed / total

    def _create_non_reconciliable_move_lines(self, data):
        data = super()._create_non_reconciliable_move_lines(data)
        self.ensure_one()

        pos_receivable_account = self.config_id.journal_id.default_account_id
        if not pos_receivable_account:
            raise UserError(_("Configure a default account on the POS journal before closing the session."))

        orders = self._get_closed_orders().filtered(lambda order: not order.account_move)

        campaign_lines = orders.lines.filtered(
            lambda line: line.online_aggregator_id and (
                not float_is_zero(line.online_discount_amount, precision_rounding=self.currency_id.rounding)
                or not float_is_zero(line.aggregator_commission_amount, precision_rounding=self.currency_id.rounding)
            )
        )

        aggregator_receivables_debit = defaultdict(float)
        aggregator_receivables_credit = defaultdict(float)
        company_expenses = defaultdict(float)
        commission_expenses = defaultdict(float)
        receivable_reduction_credits = defaultdict(float)

        # Existing campaign accounting: keep the current approved logic.
        for line in campaign_lines:
            aggregator = line.online_aggregator_id
            direction = -1.0 if line.price_unit * line.qty < 0 else 1.0

            has_discount = not float_is_zero(
                line.online_discount_amount,
                precision_rounding=self.currency_id.rounding,
            )
            has_company_contribution = not float_is_zero(
                line.company_contribution_amount,
                precision_rounding=self.currency_id.rounding,
            )
            has_aggregator_contribution = not float_is_zero(
                line.aggregator_contribution_amount,
                precision_rounding=self.currency_id.rounding,
            )
            has_commission = not float_is_zero(
                line.aggregator_commission_amount,
                precision_rounding=self.currency_id.rounding,
            )

            if has_company_contribution and not aggregator.discount_expense_account_id:
                raise UserError(_(
                    "Configure company discount expense account on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))

            if (has_aggregator_contribution or has_commission) and not aggregator.receivable_account_id:
                raise UserError(_(
                    "Configure receivable account on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))

            if has_commission and not aggregator.commission_expense_account_id:
                raise UserError(_(
                    "Configure commission expense account on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))

            if has_aggregator_contribution:
                aggregator_receivables_debit[aggregator.receivable_account_id] += (
                    direction * line.aggregator_contribution_amount
                )

            if has_company_contribution:
                company_expenses[aggregator.discount_expense_account_id] += (
                    direction * line.company_contribution_amount
                )

            if has_discount:
                receivable_reduction_credits[pos_receivable_account] += (
                    direction * line.online_discount_amount
                )

            if has_commission:
                commission_expenses[aggregator.commission_expense_account_id] += (
                    direction * line.aggregator_commission_amount
                )
                aggregator_receivables_credit[aggregator.receivable_account_id] += (
                    direction * line.aggregator_commission_amount
                )

        # New feature without closing-side writes: commission accounting for normal
        # aggregator sales paid by linked aggregator payment methods, excluding orders
        # already handled by campaign lines.
        campaign_order_ids = set(campaign_lines.mapped("order_id").ids)
        for order in orders.filtered(lambda order: order.id not in campaign_order_ids):
            for aggregator, paid_amount in self._get_order_aggregator_payments(order).items():
                if float_is_zero(paid_amount, precision_rounding=order.currency_id.rounding):
                    continue
                if not aggregator.receivable_account_id:
                    raise UserError(_(
                        "Configure receivable account on aggregator %s before closing the session.",
                        aggregator.display_name,
                    ))
                if not aggregator.commission_expense_account_id:
                    raise UserError(_(
                        "Configure commission expense account on aggregator %s before closing the session.",
                        aggregator.display_name,
                    ))
                base_amount = self._get_commission_base_for_order_payment(order, paid_amount, aggregator)
                commission = order.currency_id.round(
                    base_amount * aggregator.default_commission_percent / 100.0
                )
                direction = -1.0 if paid_amount < 0 else 1.0
                commission_expenses[aggregator.commission_expense_account_id] += direction * commission
                aggregator_receivables_credit[aggregator.receivable_account_id] += direction * commission

        date = self.stop_at
        values = []

        debit_specs = [
            (account, amount, _("Aggregator campaign contribution"), "payment_term")
            for account, amount in aggregator_receivables_debit.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ] + [
            (account, amount, _("Company contribution to online campaigns"), "product")
            for account, amount in company_expenses.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ] + [
            (account, amount, _("Aggregator commission expense"), "product")
            for account, amount in commission_expenses.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ]

        credit_specs = [
            (account, amount, _("Online campaign discount receivable reduction"), "payment_term")
            for account, amount in receivable_reduction_credits.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ] + [
            (account, amount, _("Aggregator commission deduction"), "payment_term")
            for account, amount in aggregator_receivables_credit.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ]

        for account, amount, label, display_type in debit_specs:
            converted = self._amount_converter(amount, date, True)
            values.append(self._debit_amounts({
                "name": label,
                "account_id": account.id,
                "move_id": self.move_id.id,
                "display_type": display_type,
            }, amount, converted))

        for account, amount, label, display_type in credit_specs:
            converted = self._amount_converter(amount, date, True)
            values.append(self._credit_amounts({
                "name": label,
                "account_id": account.id,
                "move_id": self.move_id.id,
                "display_type": display_type,
            }, amount, converted))

        if values:
            data["MoveLine"].create(values)

        return data
