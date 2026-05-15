# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hi_reference_employee_in_journal_entries = fields.Boolean(string="Health Reference Employee In Journal Entries",
                                                              related='company_id.hi_reference_employee_in_journal_entries',
                                                              readonly=False)
    hi_account_id = fields.Many2one('account.account', 'Health Account',
                                    related='company_id.hi_account_id',
                                    readonly=False)
    before_the_expiry_date= fields.Datetime(string="Before The Expiry Date",related='company_id.before_the_expiry_date',readonly=False)


class Company(models.Model):
    _inherit = 'res.company'

    hi_reference_employee_in_journal_entries = fields.Boolean(string="Health Reference Employee In Journal Entries")
    hi_account_id = fields.Many2one('account.account', 'Health Account')
    before_the_expiry_date = fields.Datetime(string="Before The Expiry Date")