# Copyright (C) Softhealer Technologies.
# Part of Softhealer Technologies.

from odoo import api, models, fields

class Posconfiginherit(models.Model):
    """Inherits pos.config to add analytic account functionality."""
    _inherit = 'pos.config'


    sh_analytic_account = fields.Many2one(
        'account.analytic.account', string='Analytic Account')

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if not fields_list:
            return fields_list
        if "sh_analytic_account" not in fields_list:
            fields_list.append("sh_analytic_account")
        return fields_list

    def _action_to_open_ui(self):
        res = super()._action_to_open_ui()
        self.current_session_id.write(
            {'sh_analytic_account': self.sh_analytic_account})
        return res
