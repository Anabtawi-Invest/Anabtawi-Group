# -*- coding: utf-8 -*-
from odoo import fields, models

from .bank_internal_transfer_mapping import CONFIG_PARAM_DEFAULT


class BankInternalTransferDefault(models.TransientModel):
    _name = 'bank.internal.transfer.default'
    _description = 'Default Internal Transfer Value'

    default_value = fields.Char(
        string='Default Internal Transfer',
        required=True,
        help='Used on bank accounts when the selected bank has no mapping.',
    )

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'default_value' in fields_list or not fields_list:
            res['default_value'] = self.env['bank.internal.transfer.mapping'].get_default_internal_transfer()
        return res

    def action_save(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            CONFIG_PARAM_DEFAULT,
            self.default_value or '',
        )
        return {'type': 'ir.actions.act_window_close'}
