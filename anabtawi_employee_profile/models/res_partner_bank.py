# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    salary_bank_branch = fields.Char(
        string='Bank Branch (Salary)',
        help='Branch name used on the employee profile salary section.',
        groups='hr.group_hr_user',
    )
    salary_income_tax_number = fields.Char(
        string='Income Tax Number',
        groups='hr.group_hr_user',
    )
