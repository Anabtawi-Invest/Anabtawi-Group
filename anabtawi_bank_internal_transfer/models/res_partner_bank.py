# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    internal_transfer = fields.Char(
        string='Internal Transfer',
        compute='_compute_internal_transfer',
        readonly=True,
    )

    @api.depends('bank_id')
    def _compute_internal_transfer(self):
        Mapping = self.env['bank.internal.transfer.mapping']
        default_value = Mapping.get_default_internal_transfer()
        bank_ids = self.mapped('bank_id').ids
        mapping_by_bank = {
            mapping.bank_id.id: mapping.internal_transfer
            for mapping in Mapping.search([('bank_id', 'in', bank_ids)])
        }
        for bank_account in self:
            if bank_account.bank_id and bank_account.bank_id.id in mapping_by_bank:
                bank_account.internal_transfer = mapping_by_bank[bank_account.bank_id.id]
            else:
                bank_account.internal_transfer = default_value
