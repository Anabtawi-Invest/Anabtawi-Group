from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OnlineCampaignAggregator(models.Model):
    _name = "online.campaign.aggregator"
    _description = "Online Order Aggregator"
    _inherit = "pos.load.mixin"
    _order = "name"

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one("res.partner", string="Related Contact", check_company=True)
    default_commission_percent = fields.Float(
        string="Default Commission %", required=True, default=0.0, digits=(16, 4)
    )
    payment_method_ids = fields.Many2many(
        "pos.payment.method",
        "online_campaign_aggregator_payment_method_rel",
        "aggregator_id",
        "payment_method_id",
        string="POS Payment Methods",
        domain="[('company_id', 'in', [False, company_id])]",
        help="Payment methods used in POS to identify this aggregator sales.",
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)
    receivable_account_id = fields.Many2one(
        "account.account",
        string="Aggregator Receivable Account",
        domain="[('account_type', '=', 'asset_receivable'), ('company_ids', '=', company_id)]",
        check_company=True,
        help="Reconcile campaign contributions received from this aggregator here.",
    )
    discount_expense_account_id = fields.Many2one(
        "account.account",
        string="Company Discount Expense Account",
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost')), ('company_ids', '=', company_id)]",
        check_company=True,
    )
    commission_expense_account_id = fields.Many2one(
        "account.account",
        string="Commission Expense Account",
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost')), ('company_ids', '=', company_id)]",
        check_company=True,
        help="Used for settlement/vendor-bill reconciliation; campaign orders store the estimated commission.",
    )
    color = fields.Integer()
    note = fields.Text()

    _unique_name_company = models.UniqueIndex(
        "(name, company_id)", "An aggregator with this name already exists for the company."
    )

    @api.constrains("default_commission_percent")
    def _check_commission(self):
        for aggregator in self:
            if not 0 <= aggregator.default_commission_percent <= 100:
                raise ValidationError(_("Default commission must be between 0 and 100%."))

    @api.constrains("receivable_account_id")
    def _check_receivable(self):
        for aggregator in self:
            if aggregator.receivable_account_id and not aggregator.receivable_account_id.reconcile:
                raise ValidationError(_("The aggregator receivable account must allow reconciliation."))

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("active", "=", True), ("company_id", "=", config.company_id.id)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["name", "default_commission_percent", "company_id", "color", "write_date"]

