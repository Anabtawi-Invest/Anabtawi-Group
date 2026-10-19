# Copyright (C) Softhealer Technologies.
# Part of Softhealer Technologies.

from odoo import models, fields

class Posconfiginherit(models.Model):
    """Inherits pos.config to add analytic account functionality."""
    _inherit = 'pos.config'


    sh_analytic_account = fields.Many2one(
        'account.analytic.account', string='Analytic Account')

    def _action_to_open_ui(self):
        res = super()._action_to_open_ui()
        self.current_session_id.write(
            {'sh_analytic_account': self.sh_analytic_account})
        return res
