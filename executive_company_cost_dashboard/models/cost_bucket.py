# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .classifier import INCOME_TYPES


class CeoCostBucket(models.Model):
    _name = "ceo.cost.bucket"
    _description = "Executive Cost & Profit Bucket"
    _order = "sequence, id"

    name = fields.Char(string="Bucket Name", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    category_type = fields.Selection(
        [
            ("revenue", "Revenue"),
            ("other_income", "Other Income"),
            ("cogs", "Cost of Revenue (legacy)"),
            ("expense", "Cost / Expense"),
        ],
        string="Financial Family",
        required=True,
        default="expense",
        help="Revenue and Other Income buckets only accept income accounts; "
        "cost buckets only accept expense, cost of revenue and depreciation accounts.",
    )
    color = fields.Char(string="Color", default="#3b82f6")
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)
    mapping_ids = fields.One2many("ceo.cost.account.mapping", "bucket_id", string="Mapped Accounts")
    account_count = fields.Integer(string="Accounts", compute="_compute_account_count")

    _code_unique = models.Constraint("UNIQUE(code)", "A bucket code must be unique.")

    @api.depends("mapping_ids")
    def _compute_account_count(self):
        counts = dict(
            (b.id, c)
            for b, c in self.env["ceo.cost.account.mapping"]._read_group(
                [("bucket_id", "in", self.ids)], ["bucket_id"], ["__count"]
            )
        )
        for rec in self:
            rec.account_count = counts.get(rec.id, 0)



class CeoCostAccountMapping(models.Model):
    _name = "ceo.cost.account.mapping"
    _description = "Account to Cost Bucket Mapping"
    _rec_name = "account_id"
    _order = "bucket_id, account_id"

    bucket_id = fields.Many2one("ceo.cost.bucket", string="Bucket", required=True, ondelete="cascade", index=True)
    account_id = fields.Many2one(
        "account.account", string="Ledger Account", required=True, ondelete="cascade", index=True
    )
    account_code = fields.Char(related="account_id.code", string="Code")
    account_type = fields.Selection(related="account_id.account_type", string="Account Type")
    auto = fields.Boolean(
        string="Auto-classified",
        default=False,
        help="Set by the Smart Scanner. Auto-classified rows are refreshed on re-scan; "
        "rows you create or change by hand are never overwritten.",
    )

    _account_unique = models.Constraint(
        "UNIQUE(account_id)", "Each account can only be mapped to one bucket."
    )

    @api.constrains("bucket_id", "account_id")
    def _check_family(self):
        for rec in self:
            account_is_income = rec.account_id.account_type in INCOME_TYPES
            bucket_is_income = rec.bucket_id.category_type in ("revenue", "other_income")
            if account_is_income != bucket_is_income:
                raise ValidationError(
                    _(
                        "Account %(account)s is a %(atype)s account and cannot be placed in the bucket '%(bucket)s'.",
                        account=rec.account_id.display_name,
                        atype=dict(rec.account_id._fields["account_type"].selection).get(rec.account_id.account_type),
                        bucket=rec.bucket_id.name,
                    )
                )

    def write(self, vals):
        # A manual edit takes the row out of the scanner's hands
        if "bucket_id" in vals and "auto" not in vals and not self.env.context.get("ecd_scan"):
            vals = dict(vals, auto=False)
        return super().write(vals)

    @api.model
    def _account_info(self, accounts):
        """{account_id: (code, name)} that also works for accounts shared between companies."""
        info = {}
        for acc in accounts.sudo():
            code = acc.code
            if not code:
                for company in acc.company_ids:
                    code = acc.with_company(company).code
                    if code:
                        break
            info[acc.id] = (code or "", acc.name or "")
        return info
