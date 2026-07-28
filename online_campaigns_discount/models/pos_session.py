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
        """Find the receivable/payment account used by the POS payment flow.

        If the Talabat/Careem payment method is configured directly on the
        aggregator receivable account, this method returns that account and the
        module will not create an unnecessary reclassification line.
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

    def _create_non_reconciliable_move_lines(self, data):
        """Post online campaign accounting without using Sales as recovery.

        Correct Anabtawi flow:
        - Standard POS keeps posting Sales, VAT, COGS, Inventory and payment.
          Core Sales lines are already net of the FULL discount (both the
          aggregator's and the company's share).
        - If the POS payment account is not the aggregator receivable, customer
          collections are reclassified from POS receivable to aggregator receivable.
        - The aggregator's recoverable share is debited to the aggregator
          receivable (a real asset - it will be reimbursed) and folded directly
          into each item's own core Sales line (topping up the credit that
          core POS already posted for that product), rather than added as a
          separate line. This spreads the aggregator's discount back across
          the items proportionally to each item's own discount, and scales
          automatically as items/campaigns change - nothing is hardcoded.
        - The company's own share of the discount is left exactly as core
          POS already posts it: silently netted into a lower Sales figure.
          No separate expense/recovery line is created for it.
        - Commission is debited to commission expense and credited to aggregator
          receivable, so settlement closes against the aggregator receivable.
        - Net effect: each product's Sales line = core net sale + that
          product's own aggregator_contribution_amount. Total reported
          profit is unchanged; only Sales presentation changes.
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
        commission_expenses = defaultdict(float)
        aggregator_sales_topup = defaultdict(float)
        customer_collection_reclass_debits = defaultdict(float)
        pos_collection_reclass_credits = defaultdict(float)

        for line in lines:
            aggregator = line.online_aggregator_id
            direction = -1.0 if line.price_unit * line.qty < 0 else 1.0

            has_aggregator_contribution = not float_is_zero(
                line.aggregator_contribution_amount, precision_rounding=self.currency_id.rounding
            )
            has_commission = not float_is_zero(
                line.aggregator_commission_amount, precision_rounding=self.currency_id.rounding
            )
            has_customer_collection = not float_is_zero(
                line.online_customer_paid_amount, precision_rounding=self.currency_id.rounding
            )

            if (has_customer_collection or has_aggregator_contribution or has_commission) and not aggregator.receivable_account_id:
                raise UserError(_(
                    "Configure receivable account on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))

            if has_customer_collection and pos_receivable_account != aggregator.receivable_account_id and not pos_receivable_account:
                raise UserError(_(
                    "Could not determine the POS receivable account for aggregator customer collection reclassification. "
                    "Configure the payment method account or set the aggregator payment method directly to the aggregator receivable account."
                ))

            if has_commission and not aggregator.commission_expense_account_id:
                raise UserError(_(
                    "Configure commission expense account on aggregator %s before closing the session.",
                    aggregator.display_name,
                ))

            if has_customer_collection and pos_receivable_account != aggregator.receivable_account_id:
                amount = direction * line.online_customer_paid_amount
                customer_collection_reclass_debits[aggregator.receivable_account_id] += amount
                pos_collection_reclass_credits[pos_receivable_account] += amount

            if has_aggregator_contribution:
                income_account = (
                    line.product_id.property_account_income_id
                    or line.product_id.categ_id.property_account_income_categ_id
                )
                if not income_account:
                    raise UserError(_(
                        "Configure an income account on product %s (or its category) to post "
                        "the aggregator-funded discount gross-up.",
                        line.product_id.display_name,
                    ))
                aggregator_receivables_debit[aggregator.receivable_account_id] += (
                    direction * line.aggregator_contribution_amount
                )
                aggregator_sales_topup[(income_account, line.product_id)] += (
                    direction * line.aggregator_contribution_amount
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
            (account, amount, _("Aggregator commission expense"), "product")
            for account, amount in commission_expenses.items()
            if not float_is_zero(amount, precision_rounding=self.currency_id.rounding)
        ]

        credit_specs = [
            (account, amount, _("Aggregator customer collection reclassification"), "payment_term")
            for account, amount in pos_collection_reclass_credits.items()
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

        self._apply_aggregator_sales_topup(aggregator_sales_topup)

        return data

    def _apply_aggregator_sales_topup(self, aggregator_sales_topup):
        """Increase the credit on each product's own core Sales line by its
        aggregator_contribution_amount, instead of adding a separate line.

        Core POS posts one Sales move line per (account, product, tax)
        combination for the session. We locate that exact line via its
        product_id and top up its credit - so the aggregator's share is
        folded directly into the items sold, proportional to each item's
        own discount, and needs no manual maintenance as items or discount
        percentages change.
        """
        for (account, product), amount in aggregator_sales_topup.items():
            if float_is_zero(amount, precision_rounding=self.currency_id.rounding):
                continue
            target_lines = self.move_id.line_ids.filtered(
                lambda l: l.account_id == account
                and l.product_id == product
                and l.display_type == "product"
            )
            if not target_lines:
                raise UserError(_(
                    "Could not find the Sales line for product %s on account %s to apply "
                    "the aggregator-funded discount gross-up. Configure the module's income "
                    "account to match the account core POS actually posts Sales to for this product.",
                    product.display_name, account.display_name,
                ))
            target_line = target_lines[0]
            target_line.write({"credit": target_line.credit + amount})
