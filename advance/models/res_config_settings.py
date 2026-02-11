from odoo import models, fields


class PosConfig(models.Model):
    _inherit = 'pos.config'

    pos_advance_account_id = fields.Many2one(
        'account.account',
        string='POS Advance Account',
        domain="[('account_type', '=', 'liability_current')]",
        help="Liability account for customer advance payments"
    )

    pos_cash_journal_id = fields.Many2one(
        'account.journal',
        string='POS Cash Journal',
        domain="[('type', 'in', ('cash', 'bank'))]",
        help="Journal for cash advance payments"
    )

    pos_card_journal_id = fields.Many2one(
        'account.journal',
        string='POS Card Journal',
        domain="[('type', 'in', ('cash', 'bank'))]",
        help="Journal for card advance payments"
    )

    advance_notification_user_ids = fields.Many2many(
        'res.users',
        string='Advance Notification Users',
        help="Users who will receive notifications and emails when an advance order is created for this pickup location"
    )
