from datetime import datetime, time
import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class OnlineCampaignSettlement(models.Model):
    _name = "online.campaign.settlement"
    _description = "Aggregator Campaign Settlement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_end desc, id desc"

    name = fields.Char(required=True, default="/", copy=False, tracking=True)
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("reconciled", "Reconciled")],
        default="draft", required=True, tracking=True, index=True,
    )
    aggregator_id = fields.Many2one(
        "online.campaign.aggregator", required=True, check_company=True, tracking=True, index=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    currency_id = fields.Many2one("res.currency", required=True)
    date_start = fields.Date(required=True, tracking=True)
    date_end = fields.Date(required=True, tracking=True)
    statement_reference = fields.Char(tracking=True)
    statement_file = fields.Binary(attachment=True)
    statement_filename = fields.Char()
    order_count = fields.Integer(readonly=True)
    line_count = fields.Integer(readonly=True)

    expected_customer_collections = fields.Monetary(currency_field="currency_id", readonly=True)
    expected_contribution = fields.Monetary(currency_field="currency_id", readonly=True)
    expected_commission = fields.Monetary(currency_field="currency_id", readonly=True)
    expected_net_settlement = fields.Monetary(
        currency_field="currency_id", compute="_compute_totals", store=True
    )

    actual_customer_collections = fields.Monetary(currency_field="currency_id", tracking=True)
    actual_contribution = fields.Monetary(currency_field="currency_id", tracking=True)
    actual_commission = fields.Monetary(currency_field="currency_id", tracking=True)
    adjustment_amount = fields.Monetary(
        currency_field="currency_id", tracking=True,
        help="Signed statement adjustment: positive increases the settlement, negative reduces it."
    )
    actual_net_received = fields.Monetary(
        currency_field="currency_id", compute="_compute_totals", store=True
    )
    variance_amount = fields.Monetary(
        currency_field="currency_id", compute="_compute_totals", store=True
    )
    variance_percent = fields.Float(compute="_compute_totals", store=True, digits=(16, 4))
    variance_reason = fields.Text(tracking=True)
    bank_statement_line_id = fields.Many2one(
        "account.bank.statement.line", string="Bank Statement Line", check_company=True
    )
    account_move_id = fields.Many2one(
        "account.move", string="Settlement/Commission Entry", check_company=True
    )
    reconciled_by = fields.Many2one("res.users", readonly=True, copy=False)
    reconciled_at = fields.Datetime(readonly=True, copy=False)

    @api.onchange("aggregator_id")
    def _onchange_aggregator(self):
        if self.aggregator_id:
            self.company_id = self.aggregator_id.company_id
            self.currency_id = self.aggregator_id.company_id.currency_id

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("aggregator_id"):
                aggregator = self.env["online.campaign.aggregator"].browse(values["aggregator_id"])
                values.setdefault("company_id", aggregator.company_id.id)
                values.setdefault("currency_id", aggregator.company_id.currency_id.id)
            if values.get("name", "/") == "/":
                values["name"] = _(
                    "%(aggregator)s %(start)s - %(end)s",
                    aggregator=self.env["online.campaign.aggregator"].browse(
                        values.get("aggregator_id")
                    ).display_name,
                    start=values.get("date_start", ""), end=values.get("date_end", ""),
                )
        return super().create(vals_list)

    def write(self, values):
        locked_fields = {
            "aggregator_id", "company_id", "currency_id", "date_start", "date_end",
            "actual_customer_collections", "actual_contribution", "actual_commission",
            "adjustment_amount", "statement_reference", "statement_file",
            "bank_statement_line_id", "account_move_id", "variance_reason",
            "expected_customer_collections", "expected_contribution", "expected_commission",
            "order_count", "line_count", "state",
        }
        if locked_fields.intersection(values) and self.filtered(
            lambda settlement: settlement.state == "reconciled"
        ):
            raise UserError(_("A reconciled settlement is locked."))
        return super().write(values)

    @api.depends(
        "expected_customer_collections", "expected_contribution", "expected_commission",
        "actual_customer_collections", "actual_contribution", "actual_commission",
        "adjustment_amount",
    )
    def _compute_totals(self):
        for settlement in self:
            settlement.expected_net_settlement = (
                settlement.expected_customer_collections
                + settlement.expected_contribution
                - settlement.expected_commission
            )
            settlement.actual_net_received = (
                settlement.actual_customer_collections
                + settlement.actual_contribution
                - settlement.actual_commission
                + settlement.adjustment_amount
            )
            settlement.variance_amount = (
                settlement.actual_net_received - settlement.expected_net_settlement
            )
            settlement.variance_percent = (
                settlement.variance_amount / settlement.expected_net_settlement * 100.0
                if settlement.expected_net_settlement else 0.0
            )

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for settlement in self:
            if settlement.date_start > settlement.date_end:
                raise ValidationError(_("Settlement start date cannot be after its end date."))

    @api.constrains(
        "actual_customer_collections", "actual_contribution", "actual_commission"
    )
    def _check_actual_amounts(self):
        for settlement in self:
            if any(amount < 0 for amount in (
                settlement.actual_customer_collections,
                settlement.actual_contribution,
                settlement.actual_commission,
            )):
                raise ValidationError(_("Actual settlement amounts cannot be negative."))

    def _get_campaign_lines(self):
        self.ensure_one()
        timezone = pytz.timezone(self.env.user.tz or "UTC")
        start = timezone.localize(datetime.combine(self.date_start, time.min)).astimezone(
            pytz.UTC
        ).replace(tzinfo=None)
        end = timezone.localize(datetime.combine(self.date_end, time.max)).astimezone(
            pytz.UTC
        ).replace(tzinfo=None)
        return self.env["pos.order.line"].search([
            ("online_aggregator_id", "=", self.aggregator_id.id),
            ("order_id.company_id", "=", self.company_id.id),
            ("order_id.currency_id", "=", self.currency_id.id),
            ("order_id.date_order", ">=", start),
            ("order_id.date_order", "<=", end),
            ("order_id.state", "in", ("paid", "done")),
        ])

    def action_load_expected(self):
        for settlement in self:
            if settlement.state == "reconciled":
                raise UserError(_("A reconciled settlement cannot be recalculated."))
            lines = settlement._get_campaign_lines()
            signed = lambda line, amount: -amount if line.qty * line.price_unit < 0 else amount
            settlement.write({
                "order_count": len(lines.order_id),
                "line_count": len(lines),
                "expected_customer_collections": settlement.currency_id.round(sum(
                    signed(line, line.online_customer_paid_amount) for line in lines
                )),
                "expected_contribution": settlement.currency_id.round(sum(
                    signed(line, line.aggregator_contribution_amount) for line in lines
                )),
                "expected_commission": settlement.currency_id.round(sum(
                    signed(line, line.aggregator_commission_amount) for line in lines
                )),
            })

    def action_confirm(self):
        for settlement in self:
            overlap = self.search_count([
                ("id", "!=", settlement.id),
                ("aggregator_id", "=", settlement.aggregator_id.id),
                ("company_id", "=", settlement.company_id.id),
                ("currency_id", "=", settlement.currency_id.id),
                ("state", "in", ("confirmed", "reconciled")),
                ("date_start", "<=", settlement.date_end),
                ("date_end", ">=", settlement.date_start),
            ])
            if overlap:
                raise UserError(_(
                    "This period overlaps another confirmed or reconciled settlement for the aggregator."
                ))
        self.action_load_expected()
        self.write({"state": "confirmed"})

    def action_mark_reconciled(self):
        if not self.env.user.has_group(
            "anabtawi_online_campaigns.group_online_campaign_finance_manager"
        ):
            raise AccessError(_("Only an Online Campaign Finance Manager can reconcile settlements."))
        for settlement in self:
            if settlement.state != "confirmed":
                raise UserError(_("Confirm the settlement before reconciliation."))
            if not settlement.statement_reference:
                raise UserError(_("Enter the aggregator statement reference."))
            if not settlement.bank_statement_line_id and not settlement.account_move_id:
                raise UserError(_(
                    "Link the received bank statement line or the settlement/commission accounting entry."
                ))
            if (
                not settlement.currency_id.is_zero(settlement.variance_amount)
                and not settlement.variance_reason
            ):
                raise UserError(_("Explain the settlement variance before reconciliation."))
            settlement.write({
                "state": "reconciled", "reconciled_by": self.env.user.id,
                "reconciled_at": fields.Datetime.now(),
            })

    def action_reset_to_draft(self):
        if not self.env.user.has_group(
            "anabtawi_online_campaigns.group_online_campaign_finance_manager"
        ):
            raise AccessError(_("Only an Online Campaign Finance Manager can reset settlements."))
        self.filtered(lambda settlement: settlement.state != "reconciled").write({"state": "draft"})
