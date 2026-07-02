from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosOrder(models.Model):
    _inherit = "pos.order"

    online_discount_total = fields.Monetary(
        compute="_compute_online_campaign_totals", store=True, currency_field="currency_id"
    )
    aggregator_contribution_total = fields.Monetary(
        compute="_compute_online_campaign_totals", store=True, currency_field="currency_id"
    )
    company_contribution_total = fields.Monetary(
        compute="_compute_online_campaign_totals", store=True, currency_field="currency_id"
    )
    aggregator_commission_total = fields.Monetary(
        compute="_compute_online_campaign_totals", store=True, currency_field="currency_id"
    )
    amount_before_online_discount = fields.Monetary(
        compute="_compute_online_campaign_totals", store=True, currency_field="currency_id"
    )

    @api.depends(
        "lines.price_unit", "lines.qty", "lines.online_discount_amount",
        "lines.aggregator_contribution_amount", "lines.company_contribution_amount",
        "lines.aggregator_commission_amount",
    )
    def _compute_online_campaign_totals(self):
        for order in self:
            order.online_discount_total = sum(order.lines.mapped("online_discount_amount"))
            order.aggregator_contribution_total = sum(
                order.lines.mapped("aggregator_contribution_amount")
            )
            order.company_contribution_total = sum(
                order.lines.mapped("company_contribution_amount")
            )
            order.aggregator_commission_total = sum(
                order.lines.mapped("aggregator_commission_amount")
            )
            order.amount_before_online_discount = sum(
                abs(line.price_unit * line.qty) for line in order.lines
            )


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    online_campaign_id = fields.Many2one(
        "online.discount.campaign", string="Online Campaign", ondelete="set null", index=True
    )
    online_aggregator_id = fields.Many2one(
        "online.campaign.aggregator", string="Aggregator", ondelete="set null", index=True
    )
    online_discount_percent = fields.Float(digits=(16, 4), readonly=True)
    online_discount_amount = fields.Monetary(currency_field="currency_id", readonly=True)
    aggregator_contribution_amount = fields.Monetary(currency_field="currency_id", readonly=True)
    company_contribution_amount = fields.Monetary(currency_field="currency_id", readonly=True)
    online_discount_cap_amount = fields.Monetary(currency_field="currency_id", readonly=True)
    cap_application = fields.Selection(
        [("per_order", "Per Order Cap"), ("per_line", "Per Line Cap")],
        readonly=True,
    )
    aggregator_commission_percent = fields.Float(digits=(16, 4), readonly=True)
    aggregator_commission_amount = fields.Monetary(currency_field="currency_id", readonly=True)
    online_campaign_breakdown = fields.Json(readonly=True)
    online_gross_amount = fields.Monetary(
        compute="_compute_online_reporting", store=True, currency_field="currency_id"
    )
    online_customer_paid_amount = fields.Monetary(
        compute="_compute_online_reporting", store=True, currency_field="currency_id"
    )
    online_order_date = fields.Datetime(related="order_id.date_order", store=True)
    online_session_id = fields.Many2one(related="order_id.session_id", store=True)
    online_cashier_id = fields.Many2one(related="order_id.user_id", store=True)

    @api.depends("price_subtotal_incl", "online_discount_amount")
    def _compute_online_reporting(self):
        for line in self:
            gross = abs(line.price_unit * line.qty)
            line.online_gross_amount = gross
            line.online_customer_paid_amount = abs(line.price_subtotal_incl)

    @api.constrains(
        "discount", "price_unit", "qty", "online_campaign_id", "online_aggregator_id",
        "online_discount_amount", "aggregator_contribution_amount",
        "company_contribution_amount", "online_discount_cap_amount",
        "aggregator_commission_percent", "aggregator_commission_amount",
    )
    def _check_online_amount_integrity(self):
        for line in self:
            currency = line.currency_id
            amounts = (
                line.online_discount_amount, line.aggregator_contribution_amount,
                line.company_contribution_amount, line.online_discount_cap_amount,
                line.aggregator_commission_amount,
            )
            if any(currency.compare_amounts(amount, 0.0) < 0 for amount in amounts):
                raise ValidationError(_(
                    "Online campaign discounts, caps, commissions, and contributions cannot be negative."
                ))
            has_campaign_values = any(amounts[:3]) or line.aggregator_commission_amount
            if not has_campaign_values:
                continue
            if not 0 <= line.aggregator_commission_percent <= 100:
                raise ValidationError(_("Aggregator commission must be between 0 and 100%."))
            if not line.online_campaign_id or not line.online_aggregator_id:
                raise ValidationError(_("Campaign accounting values require a campaign and aggregator."))
            if line.online_discount_amount:
                expected = currency.round(abs(line.price_unit * line.qty) * line.discount / 100.0)
                if currency.compare_amounts(expected, line.online_discount_amount) != 0:
                    raise ValidationError(_("Campaign audit amount does not match the POS line discount."))
                split = currency.round(
                    line.aggregator_contribution_amount + line.company_contribution_amount
                )
                if currency.compare_amounts(split, line.online_discount_amount) != 0:
                    raise ValidationError(_("Aggregator and company contributions must equal the discount."))
            commission_base = abs(line.price_subtotal_incl)
            expected_commission = currency.round(
                commission_base * line.aggregator_commission_percent / 100.0
            )
            if currency.compare_amounts(expected_commission, line.aggregator_commission_amount) != 0:
                raise ValidationError(_("Estimated aggregator commission does not match the net line amount."))
            if line.online_campaign_id.company_id != line.order_id.company_id:
                raise ValidationError(_("The campaign and POS order must belong to the same company."))
            if line.online_campaign_id.aggregator_id != line.online_aggregator_id:
                raise ValidationError(_("The stored aggregator does not match the campaign."))

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            "online_campaign_id", "online_aggregator_id", "online_discount_percent",
            "online_discount_amount", "aggregator_contribution_amount",
            "company_contribution_amount", "online_discount_cap_amount", "cap_application",
            "aggregator_commission_percent", "aggregator_commission_amount",
            "online_campaign_breakdown",
        ]

    def _prepare_refund_data(self, refund_order, PosPackOperationLot):
        values = super()._prepare_refund_data(refund_order, PosPackOperationLot)
        refund_quantity = abs(self.qty - self.refunded_qty)
        ratio = refund_quantity / abs(self.qty) if self.qty else 0.0
        discount_amount = self.currency_id.round(abs(self.online_discount_amount) * ratio)
        aggregator_amount = self.currency_id.round(
            abs(self.aggregator_contribution_amount) * ratio
        )
        commission_base = abs(self.price_subtotal_incl) * ratio
        values.update({
            "online_campaign_id": self.online_campaign_id.id,
            "online_aggregator_id": self.online_aggregator_id.id,
            "online_discount_percent": self.online_discount_percent,
            "online_discount_amount": discount_amount,
            "aggregator_contribution_amount": aggregator_amount,
            "company_contribution_amount": self.currency_id.round(
                discount_amount - aggregator_amount
            ),
            "online_discount_cap_amount": self.online_discount_cap_amount,
            "cap_application": self.cap_application,
            "aggregator_commission_percent": self.aggregator_commission_percent,
            "aggregator_commission_amount": self.currency_id.round(
                commission_base * self.aggregator_commission_percent / 100.0
            ),
            "online_campaign_breakdown": self.online_campaign_breakdown,
        })
        return values
