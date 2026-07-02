from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare


class OnlineDiscountCampaign(models.Model):
    _name = "online.discount.campaign"
    _description = "Online Aggregator Discount Campaign"
    _inherit = ["pos.load.mixin", "mail.thread", "mail.activity.mixin"]
    _order = "priority, start_datetime, id"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Waiting for Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    start_datetime = fields.Datetime(required=True, tracking=True, index=True)
    end_datetime = fields.Datetime(required=True, tracking=True, index=True)
    aggregator_id = fields.Many2one(
        "online.campaign.aggregator", required=True, tracking=True, check_company=True, index=True
    )
    discount_type = fields.Selection(
        [("percentage", "Percentage")], required=True, default="percentage"
    )
    discount_percent = fields.Float(required=True, digits=(16, 4), tracking=True)
    discount_cap_amount = fields.Monetary(
        default=0.0, currency_field="currency_id", tracking=True,
        help="Zero means unlimited. All allowance values remain non-negative for JoFotara."
    )
    cap_application = fields.Selection(
        [("per_unit", "Per Unit"), ("per_line", "Per Line"), ("per_order", "Per Order")],
        required=True,
        default="per_order",
        tracking=True,
    )
    pricelist_ids = fields.Many2many(
        "product.pricelist", string="POS Pricelists", required=True, tracking=True
    )
    apply_scope = fields.Selection(
        [
            ("all_products", "All Products in the Pricelist"),
            ("specific_products", "Specific Products"),
            ("specific_categories", "Specific Product Categories"),
        ],
        required=True,
        default="all_products",
        tracking=True,
    )
    product_ids = fields.Many2many("product.product", string="Products")
    category_ids = fields.Many2many("product.category", string="Product Categories")
    aggregator_commission_percent = fields.Float(
        string="Aggregator Commission %", required=True, digits=(16, 4), tracking=True
    )
    aggregator_contribution_percent = fields.Float(
        string="Aggregator Discount Contribution %", required=True, default=50.0,
        digits=(16, 4), tracking=True
    )
    company_contribution_percent = fields.Float(
        string="Company Discount Contribution %", required=True, default=50.0,
        digits=(16, 4), tracking=True
    )
    pos_config_ids = fields.Many2many(
        "pos.config", string="Point of Sale Configurations", required=True, tracking=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
        tracking=True, index=True
    )
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id
    )
    priority = fields.Integer(default=10, required=True, tracking=True, index=True)
    allow_stacking = fields.Boolean(default=False, tracking=True)
    ecommerce_approved = fields.Boolean(readonly=True, copy=False, tracking=True)
    finance_approved = fields.Boolean(readonly=True, copy=False, tracking=True)
    ecommerce_approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    ecommerce_approved_at = fields.Datetime(readonly=True, copy=False)
    finance_approved_by = fields.Many2one("res.users", readonly=True, copy=False)
    finance_approved_at = fields.Datetime(readonly=True, copy=False)
    rejection_reason = fields.Text(tracking=True)
    note = fields.Text()
    color = fields.Integer(related="aggregator_id.color", store=True)

    @api.onchange("aggregator_id")
    def _onchange_aggregator_id(self):
        if self.aggregator_id:
            self.aggregator_commission_percent = self.aggregator_id.default_commission_percent
            self.company_id = self.aggregator_id.company_id
            self.currency_id = self.aggregator_id.company_id.currency_id

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("aggregator_id"):
                aggregator = self.env["online.campaign.aggregator"].browse(values["aggregator_id"])
                values.setdefault(
                    "aggregator_commission_percent", aggregator.default_commission_percent
                )
                values.setdefault("company_id", aggregator.company_id.id)
                values.setdefault("currency_id", aggregator.company_id.currency_id.id)
        return super().create(vals_list)

    def write(self, values):
        protected = {
            "start_datetime", "end_datetime", "aggregator_id", "discount_percent",
            "discount_cap_amount", "cap_application", "pricelist_ids", "apply_scope",
            "product_ids", "category_ids", "aggregator_commission_percent",
            "aggregator_contribution_percent", "company_contribution_percent",
            "pos_config_ids", "priority", "allow_stacking",
        }
        locked = self.filtered(
            lambda campaign: campaign.state == "approved"
            or (campaign.state == "pending" and (campaign.ecommerce_approved or campaign.finance_approved))
        )
        if protected.intersection(values) and locked:
            raise UserError(_("Reset the campaign to draft before changing approved commercial terms."))
        return super().write(values)

    @api.constrains("start_datetime", "end_datetime")
    def _check_dates(self):
        for campaign in self:
            if campaign.start_datetime >= campaign.end_datetime:
                raise ValidationError(_("The campaign start must be before its end."))

    @api.constrains("discount_percent", "aggregator_commission_percent")
    def _check_percentages(self):
        for campaign in self:
            if not 0 <= campaign.discount_percent <= 100:
                raise ValidationError(_("Discount percentage must be between 0 and 100%."))
            if not 0 <= campaign.aggregator_commission_percent <= 100:
                raise ValidationError(_("Aggregator commission must be between 0 and 100%."))

    @api.constrains("discount_cap_amount")
    def _check_discount_cap(self):
        for campaign in self:
            if campaign.discount_cap_amount < 0:
                raise ValidationError(_("Discount cap cannot be negative."))

    @api.constrains("aggregator_contribution_percent", "company_contribution_percent")
    def _check_contribution_split(self):
        for campaign in self:
            total = campaign.aggregator_contribution_percent + campaign.company_contribution_percent
            if (
                campaign.aggregator_contribution_percent < 0
                or campaign.company_contribution_percent < 0
                or float_compare(total, 100.0, precision_digits=4) != 0
            ):
                raise ValidationError(_("Aggregator and company contributions must be non-negative and total 100%."))

    @api.constrains("apply_scope", "product_ids", "category_ids")
    def _check_scope_selection(self):
        for campaign in self:
            if campaign.apply_scope == "specific_products" and not campaign.product_ids:
                raise ValidationError(_("Select at least one product."))
            if campaign.apply_scope == "specific_categories" and not campaign.category_ids:
                raise ValidationError(_("Select at least one product category."))

    @api.constrains("pos_config_ids", "pricelist_ids", "company_id", "aggregator_id")
    def _check_company_configuration(self):
        for campaign in self:
            if campaign.aggregator_id.company_id != campaign.company_id:
                raise ValidationError(_("The aggregator and campaign must belong to the same company."))
            if campaign.pos_config_ids.filtered(lambda config: config.company_id != campaign.company_id):
                raise ValidationError(_("All selected points of sale must belong to the campaign company."))
            if campaign.pos_config_ids.filtered(lambda config: config.currency_id != campaign.currency_id):
                raise ValidationError(_("Selected points of sale must use the campaign currency."))
            invalid = campaign.pricelist_ids.filtered(
                lambda pricelist: pricelist.currency_id != campaign.currency_id
            )
            if invalid:
                raise ValidationError(_("Campaign pricelists must use the campaign company currency."))

    @api.constrains("state", "ecommerce_approved", "finance_approved")
    def _check_approved_state(self):
        for campaign in self:
            if campaign.state == "approved" and not (
                campaign.ecommerce_approved and campaign.finance_approved
            ):
                raise ValidationError(_("An approved campaign requires both mandatory approvals."))

    def _check_ready_for_approval(self):
        for campaign in self:
            if campaign.end_datetime <= fields.Datetime.now():
                raise UserError(_("An expired campaign cannot be submitted or approved."))
            campaign._check_scope_selection()
            campaign._check_company_configuration()

    def action_submit(self):
        if self.filtered(lambda campaign: campaign.state != "draft"):
            raise UserError(_("Only draft campaigns can be submitted."))
        self._check_ready_for_approval()
        self.write({
            "state": "pending", "ecommerce_approved": False, "finance_approved": False,
            "ecommerce_approved_by": False, "ecommerce_approved_at": False,
            "finance_approved_by": False, "finance_approved_at": False,
            "rejection_reason": False,
        })

    def _finalize_approval(self):
        for campaign in self:
            if campaign.ecommerce_approved and campaign.finance_approved:
                campaign.state = "approved"

    def action_ecommerce_approve(self):
        if not self.env.user.has_group("online_campaigns_discount.group_online_campaign_ecommerce_manager"):
            raise AccessError(_("Only an E-commerce Campaign Manager can give this approval."))
        self._check_ready_for_approval()
        for campaign in self.filtered(lambda item: item.state == "pending"):
            campaign.write({
                "ecommerce_approved": True,
                "ecommerce_approved_by": self.env.user.id,
                "ecommerce_approved_at": fields.Datetime.now(),
            })
        self._finalize_approval()

    def action_finance_approve(self):
        if not self.env.user.has_group("online_campaigns_discount.group_online_campaign_finance_manager"):
            raise AccessError(_("Only an Online Campaign Finance Manager can give this approval."))
        self._check_ready_for_approval()
        missing_accounts = self.filtered(
            lambda campaign: not campaign.aggregator_id.receivable_account_id
            or not campaign.aggregator_id.discount_expense_account_id
            or not campaign.aggregator_id.commission_expense_account_id
        )
        if missing_accounts:
            raise UserError(_(
                "Configure the aggregator receivable, company discount expense, and commission expense accounts before finance approval."
            ))
        for campaign in self.filtered(lambda item: item.state == "pending"):
            campaign.write({
                "finance_approved": True,
                "finance_approved_by": self.env.user.id,
                "finance_approved_at": fields.Datetime.now(),
            })
        self._finalize_approval()

    def action_reject(self):
        if not self.env.user.has_group("online_campaigns_discount.group_online_campaign_approver"):
            raise AccessError(_("Only a campaign approver can reject campaigns."))
        if self.filtered(lambda campaign: not campaign.rejection_reason):
            raise UserError(_("Enter a rejection reason before rejecting the campaign."))
        self.write({"state": "rejected"})

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_reset_to_draft(self):
        if not self.env.user.has_group("online_campaigns_discount.group_online_campaign_approver"):
            raise AccessError(_("Only a campaign approver can reset campaigns."))
        self.write({
            "state": "draft", "ecommerce_approved": False, "finance_approved": False,
            "ecommerce_approved_by": False, "ecommerce_approved_at": False,
            "finance_approved_by": False, "finance_approved_at": False,
        })

    def applies_to_product(self, product):
        self.ensure_one()
        if self.apply_scope == "all_products":
            return True
        if self.apply_scope == "specific_products":
            return product in self.product_ids
        category = product.product_tmpl_id.categ_id
        selected = set(self.category_ids.ids)
        while category:
            if category.id in selected:
                return True
            category = category.parent_id
        return False

    def compute_discount_amount(self, gross_amount, quantity=1.0):
        self.ensure_one()
        gross = abs(gross_amount)
        qty = abs(quantity)
        uncapped = gross * self.discount_percent / 100.0
        cap = self.discount_cap_amount
        if cap and self.cap_application == "per_unit":
            amount = min((gross / qty if qty else 0.0) * self.discount_percent / 100.0, cap) * qty
        elif cap and self.cap_application == "per_line":
            amount = min(uncapped, cap)
        else:
            amount = uncapped
        return self.currency_id.round(amount)

    def compute_order_discounts(self, line_values):
        self.ensure_one()
        remaining = self.discount_cap_amount if self.cap_application == "per_order" else 0.0
        result = []
        for gross, quantity in line_values:
            amount = self.compute_discount_amount(gross, quantity)
            if self.cap_application == "per_order" and self.discount_cap_amount:
                amount = self.currency_id.round(min(amount, remaining))
                remaining = max(0.0, remaining - amount)
            result.append(amount)
        return result

    @api.model
    def _load_pos_data_domain(self, data, config):
        now = fields.Datetime.now()
        return [
            ("active", "=", True), ("state", "=", "approved"),
            ("company_id", "=", config.company_id.id), ("pos_config_ids", "in", config.id),
            ("end_datetime", ">=", now),
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            "name", "active", "state", "start_datetime", "end_datetime", "aggregator_id",
            "discount_type", "discount_percent", "discount_cap_amount", "cap_application",
            "pricelist_ids", "apply_scope", "product_ids", "category_ids",
            "aggregator_commission_percent", "aggregator_contribution_percent",
            "company_contribution_percent", "pos_config_ids", "company_id", "currency_id",
            "priority", "allow_stacking", "write_date",
        ]
