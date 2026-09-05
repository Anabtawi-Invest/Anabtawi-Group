# -*- coding: utf-8 -*-
from odoo import fields, models


class BankInternalTransferMapping(models.Model):
    _name = 'bank.internal.transfer.mapping'
    _description = 'Bank Internal Transfer Mapping'
    _rec_name = 'bank_id'
    _order = 'bank_id'

    bank_id = fields.Many2one(
        'res.bank',
        string='Bank',
        required=True,
        ondelete='cascade',
        index=True,
    )
    internal_transfer = fields.Char(
        string='Internal Transfer',
        required=True,
        default='confirmed',
    )

    _bank_id_uniq = models.Constraint(
        'unique(bank_id)',
        'A mapping already exists for this bank.',
    )
