# -*- coding: utf-8 -*-
from odoo import models, fields


class PosConfig(models.Model):
    _inherit = 'pos.config'

    services_account_id = fields.Many2one(
        'account.account',
        string='Services Account',
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        help='Account used for employee and delivery services'
    )

    pledge_account_id = fields.Many2one(
        'account.account',
        string='Pledge Account',
        domain="[('account_type', '=', 'liability_current')]",
        help='Liability account for customer pledges'
    )

    services_journal_id = fields.Many2one(
        'account.journal',
        string='Services Journal',
        domain="[('type', 'in', ('sale', 'general'))]",
        help='Journal for employee and delivery service entries'
    )
