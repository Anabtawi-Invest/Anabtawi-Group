# Copyright (C) Softhealer Technologies.
# Part of Softhealer Technologies.



from odoo import api, fields, models

class PosPaymentInherit(models.Model):
    """Inherits pos.payment to add an analytic account."""
    _inherit = 'pos.payment'

    sh_analytic_account = fields.Many2one(
        'account.analytic.account', string='Analytic Account')

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if not fields_to_load:
            return fields_to_load
        if 'sh_analytic_account' not in fields_to_load:
            fields_to_load.append('sh_analytic_account')
        return fields_to_load
