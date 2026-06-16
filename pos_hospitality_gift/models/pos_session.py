from odoo import Command, _, fields, models


class PosSession(models.Model):
    _inherit = "pos.session"

    hospitality_settlement_move_id = fields.Many2one(
        "account.move",
        string="Hospitality Settlement Move",
        copy=False,
        readonly=True,
    )

    def _validate_session(
        self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None
    ):
        result = super()._validate_session(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs,
        )
        for session in self:
            if session.state == "closed":
                session._create_hospitality_settlement_move()
        return result

    def _create_hospitality_settlement_move(self):
        self.ensure_one()
        if self.hospitality_settlement_move_id:
            if self.hospitality_settlement_move_id.state == "draft":
                self.hospitality_settlement_move_id._post()
            return self.hospitality_settlement_move_id

        company = self.company_id
        hospitality_pm = company.hospitality_payment_method_id
        clearing_account = company.hospitality_clearing_account_id
        expense_account = company.gift_expense_account_id
        if not (hospitality_pm and clearing_account and expense_account):
            return self.env["account.move"]

        hospitality_orders = self._get_hospitality_orders(hospitality_pm)
        if not hospitality_orders:
            return self.env["account.move"]

        company_currency = company.currency_id
        amount_company_currency = 0.0
        for order in hospitality_orders:
            amount_company_currency += order.currency_id._convert(
                order.amount_total,
                company_currency,
                company,
                fields.Date.to_date(order.date_order),
            )

        if company_currency.is_zero(amount_company_currency):
            return self.env["account.move"]

        settlement_move = self.env["account.move"].create(
            {
                "journal_id": self.config_id.journal_id.id,
                "date": fields.Date.context_today(self),
                "ref": _("Hospitality settlement - %s", self.name),
                "line_ids": [
                    Command.create(
                        {
                            "name": _("Hospitality settlement expense"),
                            "account_id": expense_account.id,
                            "debit": amount_company_currency,
                            "credit": 0.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": _("Hospitality settlement clearing"),
                            "account_id": clearing_account.id,
                            "debit": 0.0,
                            "credit": amount_company_currency,
                        }
                    ),
                ],
            }
        )
        settlement_move._post()
        self.hospitality_settlement_move_id = settlement_move
        settlement_move.message_post(
            body=_("Related POS Session: %s", self._get_html_link())
        )
        return settlement_move

    def _get_hospitality_orders(self, hospitality_payment_method):
        self.ensure_one()
        closed_orders = self._get_closed_orders().filtered(lambda o: o.amount_total > 0)
        return closed_orders.filtered(
            lambda order: self._is_hospitality_order(order, hospitality_payment_method)
        )

    @staticmethod
    def _is_hospitality_order(order, hospitality_payment_method):
        non_change_payments = order.payment_ids.filtered(lambda p: not p.is_change)
        if not non_change_payments:
            return False
        return all(
            payment.payment_method_id == hospitality_payment_method
            for payment in non_change_payments
        )
