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

        The campaign discount reduction should credit the same receivable/payment
        account used by the POS order payment. Older Anabtawi POS journals do not
        always have a Default Account, so relying only on
        self.config_id.journal_id.default_account_id can break session closing.
        """
        self.ensure_one()

        # 1) Keep backward compatibility when POS journal has a default account.
        account = self.config_id.journal_id.default_account_id
        if account:
            return account

        # 2) Prefer accounts configured on the actual payment methods used by
        # campaign orders in this session.
        orders = lines.mapped("order_id")
        payment_methods = orders.mapped("payment_ids.payment_method_id")

        # Put aggregator-linked methods first, because campaign discount reduction
        # should reduce the aggregator/POS payment receivable, not cash.
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

        # 3) Fallback to account already generated on the POS session move, if any.
        # This is normally available in some Odoo flows/customizations.
        if self.move_id:
            receivable_lines = self.move_id.line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_receivable"
            )
            if receivable_lines:
                return receivable_lines[0].account_id

        return False


    def _create_non_reconciliable_move_lines(self, data):
        """Post campaign accounting without changing the POS closing workflow.

        This method intentionally follows the older stable module flow: it only adds
        accounting lines for campaign order lines already stored by the POS frontend.
        It does not scan normal aggregator payments and it does not write/update POS
        orders or POS order lines during session closing. Normal aggregator sales and
        commissions remain available through the SQL reports and settlement expected
        totals, but they are not injected into the POS close step.
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
        receivable_reduction_credits = defaultdict(float)

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

            if has_discount and not pos_receivable_account:
                raise UserError(_("Could not determine the POS receivable account for online campaign discount reduction. Configure the payment method account or the POS journal default account."))

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
