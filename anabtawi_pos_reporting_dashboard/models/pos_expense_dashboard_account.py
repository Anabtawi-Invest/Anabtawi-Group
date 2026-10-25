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
    account_id = fields.Many2one(
        "account.account",
        string="Account",
        required=True,
        ondelete="cascade",
        domain="[('account_type', 'in', ("
               "'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost'"
               "))]",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    account_code = fields.Char(related="account_id.code", string="Code")
    account_name = fields.Char(related="account_id.name", string="Account Name")

    _account_company_uniq = models.Constraint(
        "unique(account_id, company_id)",
        "This account is already configured for the expense dashboard.",
    )

    @api.onchange("account_id")
    def _onchange_account_id(self):
        if self.account_id and self.account_id.company_ids:
            if self.env.company in self.account_id.company_ids:
                self.company_id = self.env.company
            else:
                self.company_id = self.account_id.company_ids[:1]
