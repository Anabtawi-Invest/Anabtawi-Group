from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    profit_account_id = fields.Many2one(
        domain="""
            [('account_type', 'in', (
                'income',
                'income_other',
                'asset_receivable',
                'asset_cash',
                'asset_current',
                'asset_non_current',
                'asset_prepayments',
                'asset_fixed',
                'expense',
                'liability_payable',
                'liability_credit_card',
                'liability_current',
                'liability_non_current'
            ))]
        """
    )
    loss_account_id = fields.Many2one(
        domain="""
            [('account_type', 'in', (
                'expense',
                'liability_payable',
                'liability_credit_card',
                'liability_current',
                'liability_non_current',
                'asset_cash',
                'asset_current',
                'asset_non_current',
                'asset_prepayments',
                'asset_fixed',
                
            ))]
        """
    )
