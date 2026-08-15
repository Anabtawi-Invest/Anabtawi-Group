import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import format_datetime, formatLang

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    delivery_line_ids = fields.One2many(
        "pos.session.delivery.line",
        "session_id",
        string="Delivery Lines",
        readonly=True,
        copy=False,
    )
    delivery_amount = fields.Monetary(
        string="Delivery Amount",
        compute="_compute_delivery_totals",
        store=True,
        readonly=True,
        copy=False,
        tracking=True,
    )
    delivery_move_id = fields.Many2one(
        "account.move",
        string="Delivery Journal Entry",
        compute="_compute_delivery_totals",
        store=True,
        readonly=True,
        copy=False,
        tracking=True,
        help="Journal entry of the latest delivery amount line.",
    )
    delivery_report_line_id = fields.Many2one(
        "pos.delivery.amount.report.line",
        string="Delivery Report Line",
        readonly=True,
        copy=False,
    )

    @api.depends(
        "payment_method_ids",
        "order_ids",
        "cash_register_balance_start",
        "cash_register_balance_end_real",
        "statement_line_ids.amount",
        "delivery_line_ids.amount",
        "delivery_line_ids.is_closing_delivery",
    )
    def _compute_cash_balance(self):
        """Subtract in-session deliveries only; closing deliveries are accounting-only."""
        super()._compute_cash_balance()
        for session in self:
            delivered = session._get_session_delivered_total()
            if session.currency_id.is_zero(delivered):
                continue
            session.cash_register_balance_end = session.currency_id.round(
                session.cash_register_balance_end - delivered
            )
            session.cash_register_difference = session.currency_id.round(
                session.cash_register_balance_end_real - session.cash_register_balance_end
            )

    @api.depends("delivery_line_ids.amount", "delivery_line_ids.move_id")
    def _compute_delivery_totals(self):
        for session in self:
            session.delivery_amount = sum(session.delivery_line_ids.mapped("amount"))
            last_line = session.delivery_line_ids[-1:] if session.delivery_line_ids else self.env["pos.session.delivery.line"]
            session.delivery_move_id = last_line.move_id.id if last_line else False

    def init(self):
        self.env.cr.execute(
            """
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'pos_session'
               AND column_name = 'delivery_move_id'
             LIMIT 1
            """
        )
        if not self.env.cr.fetchone():
            return
        self.env.cr.execute(
            """
            SELECT 1 FROM information_schema.tables
             WHERE table_name = 'pos_session_delivery_line'
             LIMIT 1
            """
        )
        if not self.env.cr.fetchone():
            return
        self.env.cr.execute(
            """
            INSERT INTO pos_session_delivery_line (session_id, amount, move_id, user_id, create_uid, write_uid, create_date, write_date)
            SELECT ps.id,
                   COALESCE(ps.delivery_amount, 0),
                   ps.delivery_move_id,
                   ps.user_id,
                   ps.user_id,
                   ps.user_id,
                   COALESCE(ps.stop_at, ps.write_date, NOW() AT TIME ZONE 'UTC'),
                   COALESCE(ps.stop_at, ps.write_date, NOW() AT TIME ZONE 'UTC')
              FROM pos_session ps
             WHERE ((ps.delivery_amount IS NOT NULL AND ps.delivery_amount <> 0)
                OR ps.delivery_move_id IS NOT NULL)
               AND NOT EXISTS (
                    SELECT 1
                      FROM pos_session_delivery_line line
                     WHERE line.session_id = ps.id
               )
            """
        )

    def _get_delivery_closing_date(self):
        self.ensure_one()
        return fields.Date.to_date(self.stop_at or fields.Datetime.now())

    def _get_delivery_move_ref(self):
        self.ensure_one()
        opening_date = fields.Date.to_string(fields.Date.to_date(self.start_at)) if self.start_at else ""
        return _("Deliver Amount From %(pos)s - %(opening)s", pos=self.config_id.name, opening=opening_date)

    def _get_session_delivery_lines(self):
        self.ensure_one()
        return self.delivery_line_ids.filtered(lambda line: not line.is_closing_delivery)

    def _get_closing_delivery_lines(self):
        self.ensure_one()
        return self.delivery_line_ids.filtered("is_closing_delivery")

    def _get_session_delivered_total(self):
        self.ensure_one()
        return sum(self._get_session_delivery_lines().mapped("amount"))

    def _get_closing_delivered_total(self):
        self.ensure_one()
        return sum(self._get_closing_delivery_lines().mapped("amount"))

    def _get_delivered_total(self):
        self.ensure_one()
        return sum(self.delivery_line_ids.mapped("amount"))

    def _get_available_cash_for_delivery(self):
        self.ensure_one()
        return max(0.0, self.currency_id.round(self.cash_register_balance_end or 0.0))

    def _get_available_cash_for_closing_delivery(self):
        self.ensure_one()
        counted = self.cash_register_balance_end_real or 0.0
        already_delivered = self._get_closing_delivered_total()
        return max(0.0, self.currency_id.round(counted - already_delivered))

    def _validate_delivery_amount(self, amount):
        self.ensure_one()
        if amount is None:
            raise ValidationError(_("Delivery Amount is required."))
        if amount < 0:
            raise ValidationError(_("Delivery Amount must be positive or zero."))

        available_cash = self._get_available_cash_for_delivery()
        if self.currency_id.compare_amounts(amount, available_cash) > 0:
            _logger.warning(
                "POS delivery amount validation failed on session %s: amount=%s available_cash=%s delivered_total=%s user=%s",
                self.id,
                amount,
                available_cash,
                self._get_session_delivered_total(),
                self.env.user.id,
            )
            raise ValidationError(_("Delivery Amount cannot exceed available cash balance."))

        return available_cash

    def _validate_closing_delivery_amount(self, amount):
        self.ensure_one()
        if amount is None:
            raise ValidationError(_("Delivery Amount is required."))
        if amount < 0:
            raise ValidationError(_("Delivery Amount must be positive or zero."))

        available_cash = self._get_available_cash_for_closing_delivery()
        if self.currency_id.compare_amounts(amount, available_cash) > 0:
            raise ValidationError(_("Delivery Amount cannot exceed counted cash balance."))

        return available_cash

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

    def _create_delivery_line(self, amount, move, is_closing_delivery=False, reason=False):
        self.ensure_one()
        return self.env["pos.session.delivery.line"].sudo().create(
            {
                "session_id": self.id,
                "amount": amount,
                "move_id": move.id,
                "is_closing_delivery": is_closing_delivery,
                "reason": (reason or "").strip() or False,
            }
        )

    def _ensure_delivery_report_line(self):
        self.ensure_one()
        if not self.delivery_line_ids:
            return

        Report = self.env["pos.delivery.amount.report"]
        Line = self.env["pos.delivery.amount.report.line"]
        creation_date = fields.Date.to_date(self.start_at or fields.Datetime.now())
        report = Report.search([("creation_date", "=", creation_date)], limit=1)
        if not report:
            report = Report.create(
                {
                    "creation_date": creation_date,
                    "name": Report._report_name_for_date(creation_date),
                }
            )

        if self.delivery_report_line_id:
            line = self.delivery_report_line_id
            if line.state == "draft":
                line.real_arrived_amount = self.delivery_amount
            return

        Line.create(
            {
                "report_id": report.id,
                "session_id": self.id,
                "real_arrived_amount": self.delivery_amount,
            }
        )

    def get_delivery_amount_popup_data(self):
        self.ensure_one()
        config = self.config_id
        configured = bool(
            config.delivery_journal_id and config.delivery_intermediate_account_id
        )
        return {
            "configured": configured,
            "max_amount": self._get_available_cash_for_delivery(),
            "delivered_total": self._get_session_delivered_total(),
        }

    def get_closing_delivery_popup_data(self):
        self.ensure_one()
        config = self.config_id
        configured = bool(
            config.delivery_journal_id and config.delivery_intermediate_account_id
        )
        return {
            "configured": configured,
            "max_amount": self._get_available_cash_for_closing_delivery(),
            "delivered_total": self._get_closing_delivered_total(),
        }

    def _get_delivery_closing_moves(self):
        self.ensure_one()
        moves = []
        for index, line in enumerate(self._get_session_delivery_lines().sorted("create_date"), start=1):
            amount = line.amount or 0.0
            if self.currency_id.is_zero(amount):
                continue
            moves.append(
                {
                    "id": line.id,
                    "name": _("Cash Delivery %s", index),
                    "amount": -abs(amount),
                }
            )
        return moves

    def get_closing_control_data(self):
        data = super().get_closing_control_data()
        self.ensure_one()
        if not data.get("default_cash_details"):
            return data

        delivered_total = self._get_session_delivered_total()
        delivery_moves = self._get_delivery_closing_moves()
        delivery_total = -delivered_total if not self.currency_id.is_zero(delivered_total) else 0.0

        dc = dict(data["default_cash_details"])
        dc["delivery_total"] = self.currency_id.round(delivery_total)
        dc["delivery_moves"] = delivery_moves
        if not self.currency_id.is_zero(delivered_total):
            dc["amount"] = self.currency_id.round(dc["amount"] - delivered_total)
        data["default_cash_details"] = dc
        return data

    def _prepare_delivery_receipt_data(self, amount, move):
        self.ensure_one()
        return {
            "company_name": self.company_id.name or "",
            "pos_name": self.config_id.name or "",
            "cashier": self.env.user.name or "",
            "amount": amount,
            "formatted_amount": formatLang(self.env, amount, currency_obj=self.currency_id),
            "date": format_datetime(self.env, fields.Datetime.now()),
            "move_name": move.name if move else "",
        }

    def _post_delivery_success_message(self, amount, move):
        self.ensure_one()
        timestamp = fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        amount_label = f"{self.currency_id.symbol or ''}{amount:.2f}"
        message = _(
            "Delivery Amount processed successfully.<br/>"
            "Delivery Amount: %(amount)s<br/>"
            "Delivered Total: %(total)s<br/>"
            "User: %(user)s<br/>"
            "Journal Entry: %(move)s<br/>"
            "Date/Time: %(date)s",
            amount=amount_label,
            total=f"{self.currency_id.symbol or ''}{self.delivery_amount:.2f}",
            user=self.env.user.name,
            move=move._get_html_link(),
            date=timestamp,
        )
        self.message_post(body=message)

    def action_process_delivery_amount(self, amount, reason=False):
        """In-session cash delivery (تسليم النقد): affects available POS cash balance."""
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("You do not have access to process delivery amount."))
        if self.state == "closed":
            raise UserError(_("This session is already closed."))

        amount = float(amount or 0.0)
        if self.currency_id.compare_amounts(amount, 0.0) == 0:
            return {"successful": True}

        reason = (reason or "").strip()
        if not reason:
            raise ValidationError(_("A reason is required for in-session cash delivery."))

        self._validate_delivery_amount(amount)
        move = self._create_delivery_move(amount)
        self._create_delivery_line(amount, move, is_closing_delivery=False, reason=reason)
        self._ensure_delivery_report_line()
        self._post_delivery_success_message(amount, move)
        return {
            "successful": True,
            "receipt": self._prepare_delivery_receipt_data(amount, move),
        }

    def action_process_closing_delivery_amount(self, amount):
        """Closing delivery after cash count: journal entry only, no cash register impact."""
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("You do not have access to process delivery amount."))
        if self.state == "closed":
            raise UserError(_("This session is already closed."))

        amount = float(amount or 0.0)
        if self.currency_id.compare_amounts(amount, 0.0) == 0:
            return {"successful": True}

        self._validate_closing_delivery_amount(amount)
        move = self._create_delivery_move(amount)
        self._create_delivery_line(amount, move, is_closing_delivery=True)
        self._ensure_delivery_report_line()
        self._post_delivery_success_message(amount, move)
        return {
            "successful": True,
            "receipt": self._prepare_delivery_receipt_data(amount, move),
        }
