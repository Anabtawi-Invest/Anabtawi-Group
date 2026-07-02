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
            lambda line: line.online_campaign_id and not float_is_zero(
                line.online_discount_amount, precision_rounding=self.currency_id.rounding
            )
        )
        if not lines:
            return data

        income_amounts = defaultdict(float)
        aggregator_receivables = defaultdict(float)
        company_expenses = defaultdict(float)
        for line in lines:
            aggregator = line.online_aggregator_id
            if not aggregator.receivable_account_id or not aggregator.discount_expense_account_id:
                raise UserError(_(
                    "Configure receivable and company discount expense accounts on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))
            direction = -1.0 if line.price_unit * line.qty < 0 else 1.0
            income_account = (
                line.product_id._get_product_accounts()["income"]
                or self.config_id.journal_id.default_account_id
            )
            if not income_account:
                raise UserError(_("No income account is configured for product %s.", line.product_id.display_name))
            income_amounts[income_account] += direction * line.online_discount_amount
            aggregator_receivables[aggregator.receivable_account_id] += (
                direction * line.aggregator_contribution_amount
            )
            company_expenses[aggregator.discount_expense_account_id] += (
                direction * line.company_contribution_amount
            )

        date = self.stop_at
        values = []
        credit_converted_total = 0.0
        for account, amount in income_amounts.items():
            if float_is_zero(amount, precision_rounding=self.currency_id.rounding):
                continue
            converted = self._amount_converter(amount, date, True)
            credit_converted_total += converted
            values.append(self._credit_amounts({
                "name": _("Online campaign gross sale restoration"),
                "account_id": account.id, "move_id": self.move_id.id,
                "display_type": "product",
            }, amount, converted))

        debit_specs = [
            (account, amount, _("Aggregator campaign contribution"), "payment_term")
            for account, amount in aggregator_receivables.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ] + [
            (account, amount, _("Company contribution to online campaigns"), "product")
            for account, amount in company_expenses.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ]
        converted_so_far = 0.0
        for index, (account, amount, label, display_type) in enumerate(debit_specs):
            converted = (
                credit_converted_total - converted_so_far
                if index == len(debit_specs) - 1
                else self._amount_converter(amount, date, True)
            )
            converted_so_far += converted
            values.append(self._debit_amounts({
                "name": label, "account_id": account.id, "move_id": self.move_id.id,
                "display_type": display_type,
            }, amount, converted))
        data["MoveLine"].create(values)
        return data
