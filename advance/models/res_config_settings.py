from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    pos_advance_journal_id = fields.Many2one(
        'account.journal',
        string='POS Advance Journal',
        domain="[('type', 'in', ('cash', 'bank'))]"
    )

    pos_advance_account_id = fields.Many2one(
        'account.account',
        string='POS Advance Account',
        domain="[('account_type', '=', 'liability_current')]"
    )
    second_journal_id=fields.Many2one(
        'account.journal',
        string='POS Journal',
        domain="[('type', 'in', ('cash', 'bank'))]"
    )
    pos_cash_journal_id = fields.Many2one(
        'account.journal',
        string='POS Cash Journal'
    )

    pos_card_journal_id = fields.Many2one(
        'account.journal',
        string='POS Card Journal'
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_advance_journal_id = fields.Many2one(
        related='company_id.pos_advance_journal_id',
        readonly=False
    )

    pos_advance_account_id = fields.Many2one(
        related='company_id.pos_advance_account_id',
        readonly=False
    )
    second_journal_id=fields.Many2one(
            related='company_id.second_journal_id',
        readonly=False
        )
    pos_cash_journal_id = fields.Many2one(
        related='company_id.pos_cash_journal_id',
        string='POS Cash Journal',
    readonly = False

    )

    pos_card_journal_id = fields.Many2one(
        'account.journal',
        related='company_id.pos_card_journal_id',
        string='POS Card Journal',
        readonly=False

    )


