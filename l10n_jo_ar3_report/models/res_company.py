# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    gross_salary_rule_ids = fields.Many2many(
        'hr.salary.rule',
        'l10n_jo_ar3_company_gross_rule_rel',
        'company_id',
        'rule_id',
        string="Gross Salary Rules",
    )
    income_tax_rule_ids = fields.Many2many(
        'hr.salary.rule',
        'l10n_jo_ar3_company_tax_rule_rel',
        'company_id',
        'rule_id',
        string="Income Tax Salary Rules",
    )
    employer_display_name = fields.Char(
        string="Employer Name",
        help="Name printed on AR/3 Excel certificates. Falls back to the company name when empty.",
    )
