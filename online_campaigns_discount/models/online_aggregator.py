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

    payment_method_ids = fields.Many2many(
        "pos.payment.method",
        "online_campaign_aggregator_pos_payment_method_rel",
        "aggregator_id",
        "payment_method_id",
        string="POS Payment Methods",
        help="Payment methods used for this aggregator, e.g. Talabat, Careem, MyThings. Orders paid with these methods are tracked for aggregator reporting and commission accounting, even without campaigns.",
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
        help="Account used to reconcile customer payments, campaign contributions, commission deductions, and settlement amounts from this aggregator.",
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

    discount_recovery_account_id = fields.Many2one(
        "account.account",
        string="Campaign Discount Recovery Account",
        check_company=True,
        help="Credited with the tax-exclusive campaign discount offset. Use a dedicated campaign discount recovery/contra-discount account, not the normal sales account.",
    )

    color = fields.Integer()
    note = fields.Text()

    _unique_name_company = models.UniqueIndex(
        "(name, company_id)",
        "An aggregator with this name already exists for the company.",
    )



    def init(self):
        super().init()
        PaymentMethod = self.env["pos.payment.method"]
        if "is_cash_count" not in PaymentMethod._fields:
            return
        # Apply the same fix during module upgrade for already-linked aggregator payment methods.
        self.env.cr.execute(
            "SELECT to_regclass('online_campaign_aggregator_pos_payment_method_rel')"
        )
        if not self.env.cr.fetchone()[0]:
            return
        self.env.cr.execute("""
            UPDATE pos_payment_method ppm
               SET is_cash_count = FALSE
              FROM online_campaign_aggregator_pos_payment_method_rel rel
             WHERE rel.payment_method_id = ppm.id
               AND COALESCE(ppm.is_cash_count, FALSE) = TRUE
        """)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_aggregator_payment_methods_for_fast_pos_close()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "payment_method_ids" in vals:
            self._sync_aggregator_payment_methods_for_fast_pos_close()
        return result

    def _sync_aggregator_payment_methods_for_fast_pos_close(self):
        """Keep aggregator payment methods out of POS cash-count closing control.

        Aggregator channels such as Talabat/Careem are receivable/settlement channels,
        not physical cash drawers. If a linked payment method is marked as cash-counted,
        the POS frontend opens the Closing Control screen and asks the cashier to post
        entries manually. Disabling cash counting for linked aggregator methods keeps the
        cashier close flow automatic while the module still posts commission/accounting
        entries during the normal session close.
        """
        PaymentMethod = self.env["pos.payment.method"]
        if "is_cash_count" not in PaymentMethod._fields:
            return
        methods = self.mapped("payment_method_ids").filtered(lambda method: method.is_cash_count)
        if methods:
            methods.write({"is_cash_count": False})

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
