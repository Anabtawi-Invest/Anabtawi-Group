# -*- coding: utf-8 -*-
from odoo import api, fields, models


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
    account_code = fields.Char(related="account_id.code", string="Code")
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
            # Keep the current account selectable while editing this row.
            if rec.account_id:
                used = used - rec.account_id
            # Also hide accounts picked on other unsaved lines in the same editable list.
            siblings = (rec._origin | self) - rec
            sibling_accounts = siblings.filtered(
                lambda r, cid=company.id if company else False: r.company_id.id == cid
            ).mapped("account_id")
            rec.used_account_ids = used | sibling_accounts

    @api.onchange("account_id")
    def _onchange_account_id(self):
        if self.account_id and self.account_id.company_ids:
            if self.env.company in self.account_id.company_ids:
                self.company_id = self.env.company
            else:
                self.company_id = self.account_id.company_ids[:1]
