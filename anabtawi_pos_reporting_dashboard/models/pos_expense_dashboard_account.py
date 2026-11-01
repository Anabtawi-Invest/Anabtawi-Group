# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PosExpenseDashboardAccount(models.Model):
    """Accounts selected to appear on the Expenses Dashboard."""

    _name = "pos.expense.dashboard.account"
    _description = "Expense Dashboard Account"
    _rec_name = "account_id"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    used_account_ids = fields.Many2many(
        "account.account",
        compute="_compute_used_account_ids",
        help="Accounts already added for this company (excluded from the selector).",
    )
    account_id = fields.Many2one(
        "account.account",
        string="Account",
        required=True,
        ondelete="cascade",
        domain=(
            "[('account_type', 'in', "
            "('expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost')), "
            "('id', 'not in', used_account_ids)]"
        ),
    )
    # Real Char (not related) so Excel import can map the "Code" column here.
    account_code = fields.Char(
        string="Code",
        index=True,
        help="Chart of Accounts code. Used when importing from Excel.",
    )
    account_name = fields.Char(related="account_id.name", string="Account Name")

    _account_company_uniq = models.Constraint(
        "unique(account_id, company_id)",
        "This account is already configured for the expense dashboard.",
    )

    @api.depends("company_id", "account_id")
    def _compute_used_account_ids(self):
        """Accounts already configured for the same company, excluding the current row."""
        Account = self.env["account.account"]
        companies = self.mapped("company_id")
        used_by_company = {company.id: Account for company in companies}
        if companies:
            configured = self.with_context(active_test=False).sudo().search([
                ("company_id", "in", companies.ids),
            ])
            for company in companies:
                used_by_company[company.id] = configured.filtered(
                    lambda r, cid=company.id: r.company_id.id == cid
                ).mapped("account_id")

        for rec in self:
            company = rec.company_id
            used = used_by_company.get(company.id, Account) if company else Account
            if rec.account_id:
                used = used - rec.account_id
            siblings = (rec._origin | self) - rec
            sibling_accounts = siblings.filtered(
                lambda r, cid=company.id if company else False: r.company_id.id == cid
            ).mapped("account_id")
            rec.used_account_ids = used | sibling_accounts

    @api.onchange("account_id")
    def _onchange_account_id(self):
        if self.account_id:
            self.account_code = self.account_id.code or self.account_code
            if self.account_id.company_ids:
                if self.env.company in self.account_id.company_ids:
                    self.company_id = self.env.company
                else:
                    self.company_id = self.account_id.company_ids[:1]

    @api.onchange("account_code")
    def _onchange_account_code(self):
        if not self.account_code or self.account_id:
            return
        account = self._find_account_by_code(self.account_code, self.company_id)
        if account:
            self.account_id = account

    def _find_account_by_code(self, code, company=None):
        """Find a chart account by code in the given / current company."""
        code = (code or "").strip()
        if not code:
            return self.env["account.account"]
        company = company or self.env.company
        Account = self.env["account.account"].with_company(company).sudo()
        # Exact code match first (company-aware computed code).
        accounts = Account.search([
            ("code", "=", code),
            ("account_type", "in", (
                "expense",
                "expense_other",
                "expense_depreciation",
                "expense_direct_cost",
            )),
        ], limit=5)
        if len(accounts) == 1:
            return accounts
        if not accounts:
            # Fallback: any account with that code (still company-scoped via with_company).
            accounts = Account.search([("code", "=", code)], limit=5)
        if len(accounts) > 1:
            raise ValidationError(
                _("Multiple accounts found for code %(code)s. Use a unique code.", code=code)
            )
        return accounts

    def _prepare_vals_from_code(self, vals):
        """Fill account_id from account_code when importing by code only."""
        vals = dict(vals)
        company = self.env["res.company"].browse(
            vals.get("company_id") or self.env.company.id
        )
        code = (vals.get("account_code") or "").strip()
        account_id = vals.get("account_id")
        if not account_id and code:
            account = self._find_account_by_code(code, company)
            if not account:
                raise UserError(_("No account found for code %s.") % code)
            vals["account_id"] = account.id
            vals["account_code"] = account.code or code
        elif account_id and not code:
            account = self.env["account.account"].browse(account_id)
            vals["account_code"] = account.code or False
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        existing = self.browse()
        for vals in vals_list:
            vals = self._prepare_vals_from_code(vals)
            company_id = vals.get("company_id") or self.env.company.id
            account_id = vals.get("account_id")
            if account_id:
                found = self.with_context(active_test=False).search([
                    ("account_id", "=", account_id),
                    ("company_id", "=", company_id),
                ], limit=1)
                if found:
                    # Import-friendly: skip duplicates instead of failing the whole file.
                    existing |= found
                    continue
            prepared.append(vals)
        created = super().create(prepared) if prepared else self.browse()
        return existing | created

    def write(self, vals):
        if "account_id" in vals and "account_code" not in vals and vals.get("account_id"):
            account = self.env["account.account"].browse(vals["account_id"])
            vals = dict(vals, account_code=account.code or False)
        elif vals.get("account_code") and "account_id" not in vals:
            account = self._find_account_by_code(vals["account_code"], self.company_id[:1])
            if account:
                vals = dict(vals, account_id=account.id)
        return super().write(vals)
