import logging

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    delivery_amount = fields.Monetary(
        string="Delivery Amount",
        readonly=True,
        copy=False,
        tracking=True,
    )
    delivery_move_id = fields.Many2one(
        "account.move",
        string="Delivery Journal Entry",
        readonly=True,
        copy=False,
        tracking=True,
    )
    delivery_report_line_id = fields.Many2one(
        "pos.delivery.amount.report.line",
        string="Delivery Report Line",
        readonly=True,
        copy=False,
    )

    def _get_delivery_closing_date(self):
        self.ensure_one()
        return fields.Date.to_date(self.stop_at or fields.Datetime.now())

    def _get_delivery_move_ref(self):
        self.ensure_one()
        opening_date = fields.Date.to_string(fields.Date.to_date(self.start_at)) if self.start_at else ""
        return _("Deliver Amount From %(pos)s - %(opening)s", pos=self.config_id.name, opening=opening_date)

    def _validate_delivery_amount(self, amount):
        self.ensure_one()
        if amount is None:
            raise ValidationError(_("Delivery Amount is required."))
        if amount < 0:
            raise ValidationError(_("Delivery Amount must be positive or zero."))

        counted_cash = self.cash_register_balance_end_real or 0.0
        if self.currency_id.compare_amounts(amount, counted_cash) > 0:
            _logger.warning(
                "POS delivery amount validation failed on session %s: amount=%s counted_cash=%s user=%s",
                self.id,
                amount,
                counted_cash,
                self.env.user.id,
            )
            raise ValidationError(_("Delivery Amount cannot exceed counted cash balance."))

        return counted_cash

    def _get_delivery_accounts(self):
        self.ensure_one()
        config = self.config_id

        if not config.delivery_intermediate_account_id:
            raise UserError(_("Please configure the Delivery Intermediate Account on the POS configuration."))
        if not config.delivery_journal_id:
            raise UserError(_("Please configure the Delivery Journal on the POS configuration."))
        if config.delivery_journal_id.type != "general":
            raise UserError(_("Delivery Journal must be a miscellaneous journal."))
        if not self.cash_journal_id:
            raise UserError(_("No cash journal was found on this session."))
        if not self.cash_journal_id.default_account_id:
            raise UserError(
                _("Please configure the default account on cash journal %s.", self.cash_journal_id.display_name)
            )

        return config.delivery_intermediate_account_id, self.cash_journal_id.default_account_id

    def _create_delivery_move(self, amount):
        self.ensure_one()
        intermediate_account, cash_account = self._get_delivery_accounts()
        ref = self._get_delivery_move_ref()
        move_vals = {
            "journal_id": self.config_id.delivery_journal_id.id,
            "date": self._get_delivery_closing_date(),
            "ref": ref,
            "line_ids": [
                (
                    0,
                    0,
                    {
                        "name": ref,
                        "account_id": intermediate_account.id,
                        "debit": amount,
                        "credit": 0.0,
                    },
                ),
                (
                    0,
                    0,
                    {
                        "name": ref,
                        "account_id": cash_account.id,
                        "debit": 0.0,
                        "credit": amount,
                    },
                ),
            ],
        }
        move = self.env["account.move"].sudo().with_company(self.company_id).create(move_vals)
        move._post()
        return move

    def action_process_delivery_amount(self, amount):
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("You do not have access to process delivery amount."))
        if self.state == "closed":
            raise UserError(_("This session is already closed."))

        amount = float(amount or 0.0)
        self._validate_delivery_amount(amount)

        if self.delivery_move_id:
            if self.currency_id.compare_amounts(self.delivery_amount, amount) == 0:
                return {"successful": True}
            raise UserError(_("Delivery Amount has already been processed for this session."))

        move = self.env["account.move"]
        if self.currency_id.compare_amounts(amount, 0.0) > 0:
            move = self._create_delivery_move(amount)

        self.write(
            {
                "delivery_amount": amount,
                "delivery_move_id": move.id if move else False,
            }
        )

        timestamp = fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        amount_label = f"{self.currency_id.symbol or ''}{amount:.2f}"
        move_label = move._get_html_link() if move else _("N/A")
        message = _(
            "Delivery Amount processed successfully.<br/>"
            "Delivery Amount: %(amount)s<br/>"
            "User: %(user)s<br/>"
            "Journal Entry: %(move)s<br/>"
            "Date/Time: %(date)s",
            amount=amount_label,
            user=self.env.user.name,
            move=move_label,
            date=timestamp,
        )
        self.message_post(body=message)
        return {"successful": True}
