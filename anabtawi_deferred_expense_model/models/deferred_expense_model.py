# -*- coding: utf-8 -*-
from odoo import fields, models


class DeferredExpenseModel(models.Model):
    _name = "deferred.expense.model"
    _description = "Deferred Expense Model"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    recognition_months = fields.Integer(
        string="Number of Recognitions",
        required=True,
        default=12,
        help="Number of months over which the expense is recognized.",
    )
    prorata_temporis = fields.Boolean(
        string="Prorata Temporis",
        help="If set, recognition follows day-based computation when dates are applied.",
    )
    deferred_expense_account_id = fields.Many2one(
        "account.account",
        string="Deferred Expense Account",
        required=True,
        check_company=True,
        domain="[('account_type', '=', 'asset_current')]",
        help="Balance sheet (prepaid) account used for deferral entries.",
    )
    expense_account_id = fields.Many2one(
        "account.account",
        string="Expense Account",
        required=True,
        check_company=True,
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation'))]",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal",
        check_company=True,
        domain="[('type', '=', 'general'), ('active', '=', True)]",
        help="If empty, the company deferred expense journal from settings is used.",
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        check_company=True,
    )

    _sql_constraints = [
        (
            "recognition_months_positive",
            "CHECK(recognition_months > 0)",
            "Number of Recognitions must be greater than zero.",
        ),
    ]
