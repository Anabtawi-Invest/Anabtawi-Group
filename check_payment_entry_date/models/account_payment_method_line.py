# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    is_check_payment = fields.Boolean(
        string='Check',
        help='Confirming a payment that uses this method sets the journal entry date to today.',
    )
