# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    pos_profit_account_id = fields.Many2one(
        "account.account",
        string="POS Profit Account",
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        help="Income/Profit account used when posting the remaining payment (full total) for POS advance orders of this customer.",
    )

