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
    online_aggregator_id = fields.Many2one(
        "online.campaign.aggregator",
        string="Aggregator",
        compute="_compute_order_online_aggregator",
        store=True,
        readonly=True,
        index=True,
    )
    online_is_campaign_order = fields.Boolean(
        string="Campaign Order",
        compute="_compute_online_campaign_totals",
        store=True,
        readonly=True,
    )
    online_aggregator_order_ref = fields.Char(
        string="Aggregator Order Ref",
        copy=False,
        index=True,
        help="The aggregator's own order number (Talabat 'Order Id', Careem order id, etc.). "
        "Used to match this POS order against the aggregator statement during settlement "
        "reconciliation. Entered manually in the back office from the aggregator's order screen.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        # Core pos.order currently returns [] meaning "load all fields".
        # Keep that behavior; only append defensively if core ever returns a real whitelist.
        if not fields_to_load:
            return fields_to_load
        if "online_aggregator_order_ref" not in fields_to_load:
            fields_to_load.append("online_aggregator_order_ref")
        return fields_to_load

    @api.depends("payment_ids.payment_method_id", "company_id")
    def _compute_order_online_aggregator(self):
        Aggregator = self.env["online.campaign.aggregator"]
        for order in self:
            payment_methods = order.payment_ids.mapped("payment_method_id")
            aggregator = Aggregator.search([
                ("active", "=", True),
                ("company_id", "=", order.company_id.id),
                ("payment_method_ids", "in", payment_methods.ids),
            ], limit=1) if payment_methods else Aggregator.browse()
            order.online_aggregator_id = aggregator

    @api.constrains("online_aggregator_order_ref", "online_aggregator_id")
    def _check_online_aggregator_order_ref(self):
        for order in self:
            ref = (order.online_aggregator_order_ref or "").strip()
            aggregator = order.online_aggregator_id
            if not ref or not aggregator or not aggregator.require_order_ref:
                continue
            expected_length = aggregator.order_ref_digit_length or 10
            if not ref.isdigit() or len(ref) != expected_length:
                raise ValidationError(_(
                    "%(aggregator)s order reference must be exactly %(length)s digits, got %(value)r.",
                    aggregator=aggregator.name, length=expected_length, value=ref,
                ))

    def _get_online_payment_aggregator(self):
        self.ensure_one()
        payment_methods = self.payment_ids.mapped("payment_method_id")
        if not payment_methods:
            return self.env["online.campaign.aggregator"].browse()
        return self.env["online.campaign.aggregator"].search([
            ("active", "=", True),
            ("company_id", "=", self.company_id.id),
            ("payment_method_ids", "in", payment_methods.ids),
        ], limit=1)

    @api.depends(
        "lines.price_unit", "lines.qty", "lines.online_discount_amount",
        "lines.aggregator_contribution_amount", "lines.company_contribution_amount",
        "lines.aggregator_commission_amount",
    )
    def _compute_online_campaign_totals(self):
        orders_with_lines = self.filtered(lambda o: o.id)
        if not orders_with_lines:
            for order in self:
                order.online_discount_total = 0.0
                order.aggregator_contribution_total = 0.0
                order.company_contribution_total = 0.0
                order.aggregator_commission_total = 0.0
                order.amount_before_online_discount = 0.0
                order.online_is_campaign_order = False
            return

        # Perform read_group on pos.order.line to fetch campaign sums in bulk
        line_data = self.env["pos.order.line"].read_group(
            [("order_id", "in", orders_with_lines.ids)],
            ["order_id", "online_discount_amount:sum", "aggregator_contribution_amount:sum", "company_contribution_amount:sum", "aggregator_commission_amount:sum"],
            ["order_id"]
        )
        sums_by_order = {
            d["order_id"][0]: d
            for d in line_data
            if d.get("order_id")
        }

        # Perform bulk SQL query for before-discount totals (abs(price_unit * qty))
        self.env.cr.execute("""
            SELECT order_id, SUM(ABS(price_unit * qty))
            FROM pos_order_line
            WHERE order_id IN %s
            GROUP BY order_id
        """, [tuple(orders_with_lines.ids)])
        before_discount_sums = dict(self.env.cr.fetchall())

        for order in self:
            data = sums_by_order.get(order.id, {})
            order.online_discount_total = data.get("online_discount_amount", 0.0)
            order.aggregator_contribution_total = data.get("aggregator_contribution_amount", 0.0)
            order.company_contribution_total = data.get("company_contribution_amount", 0.0)
            order.aggregator_commission_total = data.get("aggregator_commission_amount", 0.0)
            order.amount_before_online_discount = before_discount_sums.get(order.id, 0.0)
            order.online_is_campaign_order = bool(order.online_discount_total or order.aggregator_contribution_total or order.company_contribution_total)


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
        [("per_unit", "Per Unit"), ("per_line", "Per Line"), ("per_order", "Per Order")],
        readonly=True,
    )
    aggregator_commission_percent = fields.Float(digits=(16, 4), readonly=True)
    commission_base = fields.Selection(
        [("before_tax", "Before Tax"), ("after_tax", "After Tax")],
        string="Commission Base", readonly=True, default="after_tax"
    )
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
            has_online_values = any(amounts[:3]) or line.aggregator_commission_amount
            if not has_online_values:
                continue
            if not 0 <= line.aggregator_commission_percent <= 100:
                raise ValidationError(_("Aggregator commission must be between 0 and 100%."))
            if not line.online_aggregator_id:
                raise ValidationError(_("Online aggregator accounting values require an aggregator."))
            if any(amounts[:3]) and not line.online_campaign_id:
                raise ValidationError(_("Campaign discount and contribution values require a campaign."))
            if line.online_discount_amount:
                if line.discount < 100:
                    expected = currency.round(abs(line.price_subtotal) * line.discount / (100.0 - line.discount))
                    if currency.compare_amounts(expected, line.online_discount_amount) != 0:
                        raise ValidationError(_("Campaign audit amount does not match the tax-exclusive POS line discount."))
                split = currency.round(
                    line.aggregator_contribution_amount + line.company_contribution_amount
                )
                if currency.compare_amounts(split, line.online_discount_amount) != 0:
                    raise ValidationError(_("Aggregator and company contributions must equal the discount."))
            if line.online_campaign_id:
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
            "aggregator_commission_percent", "commission_base", "aggregator_commission_amount",
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
        commission_base = abs(self.price_subtotal if self.commission_base == "before_tax" else self.price_subtotal_incl) * ratio
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
            "commission_base": self.commission_base,
            "aggregator_commission_amount": self.currency_id.round(
                commission_base * self.aggregator_commission_percent / 100.0
            ),
            "online_campaign_breakdown": self.online_campaign_breakdown,
        })
        return values
