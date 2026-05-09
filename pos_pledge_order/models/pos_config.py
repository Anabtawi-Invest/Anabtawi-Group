# -*- coding: utf-8 -*-
from odoo import models, fields


class PosConfig(models.Model):
    _inherit = 'pos.config'

    pos_pledge_liability_account_id = fields.Many2one(
        'account.account',
        string='Pledge Liability Account',
        domain="[('account_type', 'in', ('liability_current', 'liability_non_current')), ('deprecated', '=', False)]",
        check_company=True,
        help='Separate liability account for POS pledge (rahn) deposits (credit on pledge receipt; reversed on return). '
        'Independent from the advance-order POS Advance account.',
    )

    pledge_product_id = fields.Many2one(
        'product.product',
        string='Pledge Product',
        domain="[('sale_ok', '=', True)]",
        help='Product used to record pledge amount as a dedicated POS order line.',
    )
