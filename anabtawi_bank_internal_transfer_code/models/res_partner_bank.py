# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    internal_transfer = fields.Char(
        string='Internal Transfer',
        related='bank_id.internal_transfer',
        store=True,
        readonly=True,
    )
