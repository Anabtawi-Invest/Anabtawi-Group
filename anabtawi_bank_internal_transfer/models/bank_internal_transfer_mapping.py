# -*- coding: utf-8 -*-
from odoo import api, fields, models

CONFIG_PARAM_DEFAULT = 'anabtawi_bank_internal_transfer.default_value'


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
        default=lambda self: self._default_internal_transfer(),
    )

    _bank_id_uniq = models.Constraint(
        'unique(bank_id)',
        'A mapping already exists for this bank.',
    )

    @api.model
    def _default_internal_transfer(self):
        return self.get_default_internal_transfer()

    @api.model
    def get_default_internal_transfer(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            CONFIG_PARAM_DEFAULT, default=''
        ) or ''
