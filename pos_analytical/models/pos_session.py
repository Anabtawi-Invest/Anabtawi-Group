# Copyright (C) Softhealer Technologies.
# Part of Softhealer Technologies.

from odoo import models, fields, api


class PosSessionInherit(models.Model):
    """Inherits pos.session to add analytic account functionality."""
    _inherit = 'pos.session'

    sh_analytic_account = fields.Many2one(
        'account.analytic.account', string='Analytic Account', readonly=False)

    @api.model
    def _load_pos_data_models(self, config_id):
        """Loads additional models for the Point of Sale interface."""
        return super()._load_pos_data_models(config_id)+ ["account.analytic.account"]

    def _create_account_move(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        """
        Extends the base method to set the analytic account on the resulting
        account move lines for income and expense accounts.
        """
        res = super(PosSessionInherit, self)._create_account_move(balancing_account, amount_to_balance, bank_payment_method_diffs)
         # set analytic account detail in move order line
        all_related_moves = self._get_related_account_moves()
        if all_related_moves:
            for each_move in all_related_moves:
                if each_move.line_ids:
                    for line in each_move.line_ids:
                        if line.account_id.account_type == 'expense_direct_cost' or line.account_id.account_type == "income":
                            line.write({'analytic_distribution': {self.sh_analytic_account.id: 100}})
        return res
