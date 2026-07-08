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

    def _get_online_campaign_pos_receivable_account(self, lines):
        """Find the POS receivable account used by the POS payment flow.

        Anabtawi POS journals do not always have a Default Account, so the
        module must not depend only on ``journal_id.default_account_id``.
        This account is used only to reclassify aggregator customer collections
        from the POS receivable/payment account to the aggregator receivable
        account, so the settlement cycle can be closed against the aggregator.
        """
        self.ensure_one()

        account = self.config_id.journal_id.default_account_id
        if account:
            return account

        orders = lines.mapped("order_id")
        payment_methods = orders.mapped("payment_ids.payment_method_id")
        aggregator_methods = lines.mapped("online_aggregator_id.payment_method_ids")
        ordered_methods = (payment_methods & aggregator_methods) | (payment_methods - aggregator_methods)

        for method in ordered_methods:
            for field_name in (
                "receivable_account_id",
                "outstanding_account_id",
                "outstanding_receipt_account_id",
            ):
                if field_name in method._fields and method[field_name]:
                    return method[field_name]

            journal = method.journal_id if "journal_id" in method._fields else False
            if journal and journal.default_account_id:
                return journal.default_account_id

        if self.move_id:
            receivable_lines = self.move_id.line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_receivable"
            )
            if receivable_lines:
                return receivable_lines[0].account_id

        return False

    def _get_online_campaign_income_account(self, line):
        """Return the income account used to restore the tax-exclusive discount.

        POS already posts sales after discount. To show campaign economics in
        accounting without using a permanent clearing account, the module posts
        the tax-exclusive campaign discount split as:

            Dr Company Discount Expense
            Dr Aggregator Receivable
            Cr Sales / Campaign Discount Recovery

        The credit uses the product income account, matching the product revenue
        account used by Odoo's POS accounting as closely as possible.
        """
        product = line.product_id
        account = product.property_account_income_id or product.categ_id.property_account_income_categ_id
        if not account:
            raise UserError(_(
                "Configure an income account on product %s or its category before closing the POS session.",
                product.display_name,
            ))
        return account

    def _create_non_reconciliable_move_lines(self, data):
        """Post online campaign accounting using one aggregator receivable cycle.

        Accounting model:
        - Standard POS keeps posting sales, VAT, COGS, inventory, and payment.
        - The module reclassifies aggregator customer collections from the POS
          receivable/payment account to the aggregator receivable account.
        - Aggregator campaign contribution increases aggregator receivable.
        - Company contribution is posted to the configured discount expense.
        - The full tax-exclusive discount is credited to the product income
          account as campaign discount recovery, avoiding any permanent clearing
          account and avoiding a partial/fake POS receivable reduction.
        - Commission is posted as expense and deducted from aggregator receivable.
        """
        data = super()._create_non_reconciliable_move_lines(data)
        self.ensure_one()

        lines = self._get_closed_orders().filtered(lambda order: not order.account_move).lines.filtered(
            lambda line: line.online_campaign_id and line.online_aggregator_id and (
                not float_is_zero(line.online_discount_amount, precision_rounding=self.currency_id.rounding)
                or not float_is_zero(line.aggregator_commission_amount, precision_rounding=self.currency_id.rounding)
            )
        )
        if not lines:
            return data

        pos_receivable_account = self._get_online_campaign_pos_receivable_account(lines)

        aggregator_receivables_debit = defaultdict(float)
        aggregator_receivables_credit = defaultdict(float)
        company_expenses = defaultdict(float)
        commission_expenses = defaultdict(float)
        customer_collection_reclass_debits = defaultdict(float)
        pos_collection_reclass_credits = defaultdict(float)
        discount_recovery_credits = defaultdict(float)

        for line in lines:
            aggregator = line.online_aggregator_id
            direction = -1.0 if line.price_unit * line.qty < 0 else 1.0

            has_discount = not float_is_zero(
                line.online_discount_amount, precision_rounding=self.currency_id.rounding
            )
            has_aggregator_contribution = not float_is_zero(
                line.aggregator_contribution_amount, precision_rounding=self.currency_id.rounding
            )
            has_company_contribution = not float_is_zero(
                line.company_contribution_amount, precision_rounding=self.currency_id.rounding
            )
            has_commission = not float_is_zero(
                line.aggregator_commission_amount, precision_rounding=self.currency_id.rounding
            )
            has_customer_collection = not float_is_zero(
                line.online_customer_paid_amount, precision_rounding=self.currency_id.rounding
            )

            if (has_customer_collection or has_discount) and not pos_receivable_account:
                raise UserError(_(
                    "Could not determine the POS receivable account for aggregator customer collection reclassification. "
                    "Configure the payment method account or the POS journal default account."
                ))

            if (has_customer_collection or has_aggregator_contribution or has_commission) and not aggregator.receivable_account_id:
                raise UserError(_(
                    "Configure receivable account on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))

            if has_company_contribution and not aggregator.discount_expense_account_id:
                raise UserError(_(
                    "Configure company discount expense account on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))

            if has_commission and not aggregator.commission_expense_account_id:
                raise UserError(_(
                    "Configure commission expense account on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))

            if has_customer_collection:
                amount = direction * line.online_customer_paid_amount
                customer_collection_reclass_debits[aggregator.receivable_account_id] += amount
                pos_collection_reclass_credits[pos_receivable_account] += amount

            if has_aggregator_contribution:
                aggregator_receivables_debit[aggregator.receivable_account_id] += (
                    direction * line.aggregator_contribution_amount
                )

            if has_company_contribution:
                company_expenses[aggregator.discount_expense_account_id] += (
                    direction * line.company_contribution_amount
                )

            if has_discount:
                income_account = self._get_online_campaign_income_account(line)
                discount_recovery_credits[income_account] += (
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
            (account, amount, _("Aggregator customer collections"), "payment_term")
            for account, amount in customer_collection_reclass_debits.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ] + [
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
            (account, amount, _("Aggregator customer collection reclassification"), "payment_term")
            for account, amount in pos_collection_reclass_credits.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ] + [
            (account, amount, _("Online campaign discount recovery"), "product")
            for account, amount in discount_recovery_credits.items()
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
