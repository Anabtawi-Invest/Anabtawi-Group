from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PosDeliveryAmountReport(models.Model):
    _name = "pos.delivery.amount.report"
    _description = "POS Delivery Amount Report"
    _order = "creation_date desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False)
    creation_date = fields.Date(required=True, readonly=True, index=True)
    line_ids = fields.One2many("pos.delivery.amount.report.line", "report_id", string="Lines")
    currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_currency_id",
        store=True,
    )
    total_delivery_amount = fields.Monetary(compute="_compute_totals", store=True)
    total_real_arrived_amount = fields.Monetary(compute="_compute_totals", store=True)
    total_difference = fields.Monetary(compute="_compute_totals", store=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("transferred", "Transferred"),
        ],
        default="draft",
        required=True,
        readonly=True,
    )

    _sql_constraints = [
        ("creation_date_unique", "unique(creation_date)", "A delivery report already exists for this date."),
    ]

    @api.depends("line_ids.currency_id")
    def _compute_currency_id(self):
        company_currency = self.env.company.currency_id
        for report in self:
            report.currency_id = report.line_ids[:1].currency_id or company_currency

    @api.depends("line_ids.delivery_amount", "line_ids.real_arrived_amount", "line_ids.difference")
    def _compute_totals(self):
        for report in self:
            report.total_delivery_amount = sum(report.line_ids.mapped("delivery_amount"))
            report.total_real_arrived_amount = sum(report.line_ids.mapped("real_arrived_amount"))
            report.total_difference = sum(report.line_ids.mapped("difference"))

    @api.model
    def _report_name_for_date(self, date_value):
        return _("Delivery Amount for Session %(date)s", date=fields.Date.to_string(date_value))

    @api.model
    def action_generate_reports(self):
        session_domain = [
            ("state", "=", "closed"),
            ("delivery_amount", "!=", False),
            ("delivery_report_line_id", "=", False),
        ]
        sessions = self.env["pos.session"].search(session_domain, order="create_date asc")
        sessions_by_date = defaultdict(lambda: self.env["pos.session"])
        for session in sessions:
            sessions_by_date[fields.Date.to_date(session.create_date)] |= session

        for creation_date, day_sessions in sessions_by_date.items():
            report = self.search([("creation_date", "=", creation_date)], limit=1)
            if not report:
                report = self.create(
                    {
                        "creation_date": creation_date,
                        "name": self._report_name_for_date(creation_date),
                    }
                )
            self.env["pos.delivery.amount.report.line"].create(
                [
                    {
                        "report_id": report.id,
                        "session_id": session.id,
                        "real_arrived_amount": session.delivery_amount or 0.0,
                    }
                    for session in day_sessions
                ]
            )
        return True

    def action_transfer_all(self):
        for report in self:
            draft_lines = report.line_ids.filtered(lambda line: line.state == "draft")
            if not draft_lines:
                continue
            for line in draft_lines:
                line.action_transfer()
            report._compute_state()
        return True

    def _compute_state(self):
        for report in self:
            report.state = "transferred" if report.line_ids and all(
                line.state == "transferred" for line in report.line_ids
            ) else "draft"


class PosDeliveryAmountReportLine(models.Model):
    _name = "pos.delivery.amount.report.line"
    _description = "POS Delivery Amount Report Line"
    _order = "id desc"

    report_id = fields.Many2one("pos.delivery.amount.report", required=True, ondelete="cascade", index=True)
    session_id = fields.Many2one("pos.session", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one(related="session_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="session_id.currency_id", store=True, readonly=True)
    pos_config_id = fields.Many2one(related="session_id.config_id", store=True, readonly=True)
    delivery_amount = fields.Monetary(related="session_id.delivery_amount", readonly=True)
    real_arrived_amount = fields.Monetary(required=True, default=0.0)
    difference = fields.Monetary(compute="_compute_difference", store=True)
    settlement_move_id = fields.Many2one("account.move", readonly=True, copy=False)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("transferred", "Transferred"),
        ],
        default="draft",
        required=True,
        readonly=True,
    )

    _sql_constraints = [
        ("session_unique", "unique(session_id)", "A report line already exists for this POS session."),
    ]

    @api.depends("delivery_amount", "real_arrived_amount")
    def _compute_difference(self):
        for line in self:
            line.difference = (line.delivery_amount or 0.0) - (line.real_arrived_amount or 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        reports = self.env["pos.delivery.amount.report"]
        for rec in records:
            rec.session_id.delivery_report_line_id = rec.id
            reports |= rec.report_id
        reports._compute_state()
        return records

    def unlink(self):
        reports = self.report_id
        sessions = self.session_id
        res = super().unlink()
        sessions.write({"delivery_report_line_id": False})
        reports._compute_state()
        return res

    @api.constrains("real_arrived_amount")
    def _check_real_arrived_amount(self):
        for line in self:
            if line.real_arrived_amount < 0:
                raise ValidationError(_("Real Arrived Amount must be positive or zero."))

    def _check_required_accounts(self):
        self.ensure_one()
        config = self.session_id.config_id
        if not config.delivery_intermediate_account_id:
            raise UserError(_("Please configure the Delivery Intermediate Account on the POS settings."))
        if not config.main_holding_cash_fund_account_id:
            raise UserError(_("Please configure the Main Holding Cash Fund account on the POS settings."))
        if not config.delivery_amount_difference_account_id:
            raise UserError(
                _("Please configure the Differences between Delivery Amount and Real Amount account on the POS settings.")
            )
        if not config.delivery_journal_id:
            raise UserError(_("Please configure the Delivery Journal on the POS settings."))
        return (
            config.delivery_intermediate_account_id,
            config.main_holding_cash_fund_account_id,
            config.delivery_amount_difference_account_id,
            config.delivery_journal_id,
        )

    def action_transfer(self):
        for line in self:
            if line.state == "transferred":
                continue

            delivery_account, main_holding_account, difference_account, journal = line._check_required_accounts()
            delivery_amount = line.delivery_amount or 0.0
            real_amount = line.real_arrived_amount or 0.0
            difference = delivery_amount - real_amount

            if line.currency_id.compare_amounts(delivery_amount, 0.0) == 0 and line.currency_id.compare_amounts(real_amount, 0.0) == 0:
                line.write({"state": "transferred"})
                line.report_id._compute_state()
                continue

            move_date = line.report_id.creation_date or fields.Date.context_today(line)
            ref = _(
                "Delivery Settlement %(session)s",
                session=line.session_id.name,
            )
            move_lines = [
                (
                    0,
                    0,
                    {
                        "name": ref,
                        "account_id": delivery_account.id,
                        "credit": delivery_amount,
                        "debit": 0.0,
                    },
                ),
                (
                    0,
                    0,
                    {
                        "name": ref,
                        "account_id": main_holding_account.id,
                        "debit": real_amount,
                        "credit": 0.0,
                    },
                ),
            ]
            if line.currency_id.compare_amounts(difference, 0.0) > 0:
                move_lines.append(
                    (
                        0,
                        0,
                        {
                            "name": _("Delivery Difference - Deficit"),
                            "account_id": difference_account.id,
                            "debit": difference,
                            "credit": 0.0,
                        },
                    )
                )
            elif line.currency_id.compare_amounts(difference, 0.0) < 0:
                move_lines.append(
                    (
                        0,
                        0,
                        {
                            "name": _("Delivery Difference - Surplus"),
                            "account_id": difference_account.id,
                            "debit": 0.0,
                            "credit": abs(difference),
                        },
                    )
                )

            move = self.env["account.move"].with_company(line.company_id).create(
                {
                    "journal_id": journal.id,
                    "date": move_date,
                    "ref": ref,
                    "line_ids": move_lines,
                }
            )
            move._post()

            line.write(
                {
                    "settlement_move_id": move.id,
                    "state": "transferred",
                }
            )
            line.session_id.message_post(
                body=_(
                    "Delivery settlement posted successfully.<br/>"
                    "Real Arrived Amount: %(real)s<br/>"
                    "Difference: %(diff)s<br/>"
                    "Journal Entry: %(move)s",
                    real=real_amount,
                    diff=difference,
                    move=move._get_html_link(),
                )
            )
            line.report_id._compute_state()
        return True
