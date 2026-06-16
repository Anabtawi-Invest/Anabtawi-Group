import logging

from odoo import Command, _, fields, models

_logger = logging.getLogger(__name__)


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
                _logger.warning(
                    "[POS_HOSPITALITY_GIFT] Session %s closed, attempting hospitality settlement",
                    session.name,
                )
                session._create_hospitality_settlement_move()
            else:
                _logger.warning(
                    "[POS_HOSPITALITY_GIFT] Session %s is not closed (state=%s), skip settlement",
                    session.name,
                    session.state,
                )
        return result

    def _create_hospitality_settlement_move(self):
        self.ensure_one()
        if self.hospitality_settlement_move_id:
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s already linked to settlement move %s (state=%s)",
                self.name,
                self.hospitality_settlement_move_id.name,
                self.hospitality_settlement_move_id.state,
            )
            if self.hospitality_settlement_move_id.state == "draft":
                _logger.warning(
                    "[POS_HOSPITALITY_GIFT] Posting existing draft settlement move %s",
                    self.hospitality_settlement_move_id.name,
                )
                self.hospitality_settlement_move_id._post()
            return self.hospitality_settlement_move_id

        company = self.company_id
        hospitality_pm = company.hospitality_payment_method_id
        clearing_account = company.hospitality_clearing_account_id
        expense_account = company.gift_expense_account_id
        if not (hospitality_pm and clearing_account and expense_account):
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s skip: missing configuration "
                "(hospitality_pm=%s, clearing_account=%s, expense_account=%s)",
                self.name,
                hospitality_pm.id if hospitality_pm else False,
                clearing_account.id if clearing_account else False,
                expense_account.id if expense_account else False,
            )
            return self.env["account.move"]

        hospitality_orders = self._get_hospitality_orders(hospitality_pm)
        if not hospitality_orders:
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s skip: no hospitality orders found",
                self.name,
            )
            return self.env["account.move"]

        company_currency = company.currency_id
        amount_company_currency = 0.0
        for order in hospitality_orders:
            converted_amount = order.currency_id._convert(
                order.amount_total,
                company_currency,
                company,
                fields.Date.to_date(order.date_order),
            )
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s order %s included in settlement: amount_total=%s %s, converted=%s %s",
                self.name,
                order.name,
                order.amount_total,
                order.currency_id.name,
                converted_amount,
                company_currency.name,
            )
            amount_company_currency += order.currency_id._convert(
                order.amount_total,
                company_currency,
                company,
                fields.Date.to_date(order.date_order),
            )

        if company_currency.is_zero(amount_company_currency):
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s skip: aggregated amount is zero (%s %s)",
                self.name,
                amount_company_currency,
                company_currency.name,
            )
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
        _logger.warning(
            "[POS_HOSPITALITY_GIFT] Session %s settlement move created: %s, amount=%s %s",
            self.name,
            settlement_move.name,
            amount_company_currency,
            company_currency.name,
        )
        settlement_move.message_post(
            body=_("Related POS Session: %s", self._get_html_link())
        )
        return settlement_move

    def _get_hospitality_orders(self, hospitality_payment_method):
        self.ensure_one()
        closed_orders = self._get_closed_orders().filtered(lambda o: o.amount_total > 0)
        hospitality_orders = self.env["pos.order"]
        for order in closed_orders:
            is_hospitality_order = self._is_hospitality_order(order, hospitality_payment_method)
            _logger.warning(
                "[POS_HOSPITALITY_GIFT] Session %s order %s hospitality check=%s payments=%s",
                self.name,
                order.name,
                is_hospitality_order,
                [
                    {
                        "method_id": p.payment_method_id.id,
                        "method_name": p.payment_method_id.name,
                        "amount": p.amount,
                        "is_change": p.is_change,
                    }
                    for p in order.payment_ids
                ],
            )
            if is_hospitality_order:
                hospitality_orders |= order
        return hospitality_orders

    @staticmethod
    def _is_hospitality_order(order, hospitality_payment_method):
        non_change_payments = order.payment_ids.filtered(lambda p: not p.is_change)
        if not non_change_payments:
            return False
        return all(
            payment.payment_method_id == hospitality_payment_method
            for payment in non_change_payments
        )
