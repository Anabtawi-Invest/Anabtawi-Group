# Copyright (C) Softhealer Technologies.
# Part of Softhealer Technologies.

from odoo import models, fields, api


class PosOrderInherit (models.Model):
    """Inherits pos.order to add analytic account functionality."""
    _inherit = 'pos.order'

    sh_pos_order_analytic_account = fields.Many2one(
        'account.analytic.account', string="Analytic Account")

    @api.model
    def _order_fields(self, ui_order):
        """
        Overrides the base method to include the analytic account from the UI order.

        Args:
            ui_order (dict): The order data from the Point of Sale UI.

        Returns:
            dict: The updated order fields dictionary.
        """
        res = super()._order_fields(ui_order)
        # pass analytic accuount data in pos order
        if res:
            if ui_order.get('sh_pos_order_analytic_account'):
                res.update({'sh_pos_order_analytic_account': ui_order.get(
                    'sh_pos_order_analytic_account')})

        return res

    def _payment_fields(self, order, ui_paymentline):
        """
        Overrides the base method to include the analytic account in payment lines.

        Args:
            order (recordset): The Point of Sale order.
            ui_paymentline (dict): The payment line data from the UI.

        Returns:
            dict: The updated payment fields dictionary.
        """
        # pass analyic account data  in payment lines.
        res = super()._payment_fields(order, ui_paymentline)
        res['sh_analytic_account'] = ui_paymentline.get('sh_analytic_account')
        return res


class PosOrderlineInherit(models.Model):
    """Inherits pos.order.line to link analytic account from the order."""
    _inherit = 'pos.order.line'

    sh_pos_order_analytic_account = fields.Many2one(
        'account.analytic.account',
        related='order_id.sh_pos_order_analytic_account', string="Analytic Account", readonly=False)
