# Copyright (C) Softhealer Technologies.
# Part of Softhealer Technologies.



from odoo import models, fields

class PosPaymentInherit(models.Model):
    """Inherits pos.payment to add an analytic account."""
    _inherit = 'pos.payment'

    sh_analytic_account = fields.Many2one(
        'account.analytic.account', string='Analytic Account')
