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

    def _prepare_non_campaign_aggregator_lines(self, orders):
        """Attach aggregator audit values to normal aggregator orders.

        Campaign orders already receive their online values from the POS UI. This method
        covers the missing case: orders paid through Talabat/Careem/etc. payment methods
        without an online campaign. It writes the aggregator and estimated commission on
        the POS lines so the reporting and settlement screens include the full aggregator
        cycle.
        """
        self.ensure_one()
        for order in orders:
            if order.lines.filtered(lambda line: line.online_campaign_id):
                continue
            aggregator = order._get_online_payment_aggregator()
            if not aggregator:
                continue
            if order.lines.filtered(lambda line: line.online_aggregator_id and line.aggregator_commission_amount):
                continue

            base_amount = abs(order.amount_total if aggregator.commission_base == "after_tax" else order.amount_total - order.amount_tax)
            commission_total = order.currency_id.round(
                base_amount * aggregator.default_commission_percent / 100.0
            )

            lines = order.lines.filtered(lambda line: not getattr(line, "display_type", False))
            if not lines:
                continue
            weight_field = "price_subtotal_incl" if aggregator.commission_base == "after_tax" else "price_subtotal"
            weights = [abs(getattr(line, weight_field)) for line in lines]
            total_weight = sum(weights) or sum(abs(line.price_unit * line.qty) for line in lines) or len(lines)

            allocated = 0.0
            for index, line in enumerate(lines):
                if index == len(lines) - 1:
                    commission_amount = order.currency_id.round(commission_total - allocated)
                else:
                    commission_amount = order.currency_id.round(commission_total * weights[index] / total_weight)
                    allocated += commission_amount
                line.write({
                    "online_aggregator_id": aggregator.id,
                    "aggregator_commission_percent": aggregator.default_commission_percent,
                    "commission_base": aggregator.commission_base,
                    "aggregator_commission_amount": commission_amount,
                    "online_campaign_breakdown": {
                        "source": "aggregator_payment_method",
                        "payment_method_ids": order.payment_ids.mapped("payment_method_id").ids,
                        "commission_base": aggregator.commission_base,
                    },
                })

    def _create_non_reconciliable_move_lines(self, data):
        data = super()._create_non_reconciliable_move_lines(data)
        self.ensure_one()

        pos_receivable_account = self.config_id.journal_id.default_account_id
        if not pos_receivable_account:
            raise UserError(_("Configure a default account on the POS journal before closing the session."))

        orders = self._get_closed_orders().filtered(lambda order: not order.account_move)
        self._prepare_non_campaign_aggregator_lines(orders)

        lines = orders.lines.filtered(
            lambda line: line.online_aggregator_id and (
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
        receivable_reduction_credits = defaultdict(float)

        for line in lines:
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
