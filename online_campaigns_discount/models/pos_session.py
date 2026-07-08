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

    def _create_non_reconciliable_move_lines(self, data):
        data = super()._create_non_reconciliable_move_lines(data)
        self.ensure_one()
        lines = self._get_closed_orders().filtered(lambda order: not order.account_move).lines.filtered(
            lambda line: line.online_campaign_id and (
                not float_is_zero(line.online_discount_amount, precision_rounding=self.currency_id.rounding)
                or not float_is_zero(line.aggregator_commission_amount, precision_rounding=self.currency_id.rounding)
            )
        )
        if not lines:
            return data

        aggregator_receivables_debit = defaultdict(float)
        aggregator_receivables_credit = defaultdict(float)
        company_expenses = defaultdict(float)
        commission_expenses = defaultdict(float)
        clearing_credits = defaultdict(float)

        for line in lines:
            aggregator = line.online_aggregator_id
            direction = -1.0 if line.price_unit * line.qty < 0 else 1.0

            if not aggregator.discount_clearing_account_id:
                raise UserError(_(
                    "Configure campaign discount clearing account on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))
            if not aggregator.discount_expense_account_id:
                raise UserError(_(
                    "Configure company discount expense account on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))

            has_aggregator_contribution = not float_is_zero(
                line.aggregator_contribution_amount, precision_rounding=self.currency_id.rounding
            )
            has_commission = not float_is_zero(
                line.aggregator_commission_amount, precision_rounding=self.currency_id.rounding
            )
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
            if not float_is_zero(line.company_contribution_amount, precision_rounding=self.currency_id.rounding):
                company_expenses[aggregator.discount_expense_account_id] += (
                    direction * line.company_contribution_amount
                )
            if not float_is_zero(line.online_discount_amount, precision_rounding=self.currency_id.rounding):
                clearing_credits[aggregator.discount_clearing_account_id] += (
                    direction * line.online_discount_amount
                )
            if has_commission:
                commission_expenses[aggregator.commission_expense_account_id] += (
                    direction * line.aggregator_commission_amount
                )
                aggregator_receivables_credit[aggregator.receivable_account_id] += (
                    direction * line.aggregator_commission_amount
                )

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
            (account, amount, _("Online campaign discount clearing"), "product")
            for account, amount in clearing_credits.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ] + [
            (account, amount, _("Aggregator commission deduction"), "payment_term")
            for account, amount in aggregator_receivables_credit.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ]

        for account, amount, label, display_type in debit_specs:
            converted = self._amount_converter(amount, date, True)
            values.append(self._debit_amounts({
                "name": label, "account_id": account.id, "move_id": self.move_id.id,
                "display_type": display_type,
            }, amount, converted))
        for account, amount, label, display_type in credit_specs:
            converted = self._amount_converter(amount, date, True)
            values.append(self._credit_amounts({
                "name": label, "account_id": account.id, "move_id": self.move_id.id,
                "display_type": display_type,
            }, amount, converted))

        if values:
            data["MoveLine"].create(values)
        return data
