# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    gross_salary_rule_ids = fields.Many2many(
        related='company_id.gross_salary_rule_ids',
        readonly=False,
    )
    income_tax_rule_ids = fields.Many2many(
        related='company_id.income_tax_rule_ids',
        readonly=False,
    )
    employer_display_name = fields.Char(
        related='company_id.employer_display_name',
        readonly=False,
    )
