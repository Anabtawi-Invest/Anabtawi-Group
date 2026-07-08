from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OnlineCampaignAggregator(models.Model):
    _name = "online.campaign.aggregator"
    _description = "Online Order Aggregator"
    _inherit = "pos.load.mixin"
    _order = "name"

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Related Contact",
        check_company=True,
    )

    default_commission_percent = fields.Float(
        string="Default Commission %",
        required=True,
        default=0.0,
        digits=(16, 4),
    )

    commission_base = fields.Selection(
        [
            ("before_tax", "Sales Amount Before Tax"),
            ("after_tax", "Sales Amount After Tax"),
        ],
        string="Commission Base",
        default="after_tax",
        required=True,
        help="Choose whether the aggregator commission is calculated before or after sales tax.",
    )

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    currency_id = fields.Many2one(
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    receivable_account_id = fields.Many2one(
        "account.account",
        string="Aggregator Receivable Account",
        check_company=True,
        help="Account used to reconcile customer payments, campaign contributions and settlements.",
    )

    discount_expense_account_id = fields.Many2one(
        "account.account",
        string="Company Discount Expense Account",
        check_company=True,
        help="Account used to record the company-funded share of online campaign discounts.",
    )

    commission_expense_account_id = fields.Many2one(
        "account.account",
        string="Commission Expense Account",
        check_company=True,
        help="Account used to record aggregator commissions.",
    )

    color = fields.Integer()
    note = fields.Text()

    _unique_name_company = models.UniqueIndex(
        "(name, company_id)",
        "An aggregator with this name already exists for the company.",
    )

    @api.constrains("default_commission_percent")
    def _check_commission(self):
        for aggregator in self:
            if not 0 <= aggregator.default_commission_percent <= 100:
                raise ValidationError(_("Default commission must be between 0 and 100%."))

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [
            ("active", "=", True),
            ("company_id", "=", config.company_id.id),
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            "name",
            "default_commission_percent",
            "commission_base",
            "company_id",
            "color",
            "write_date",
        ]
