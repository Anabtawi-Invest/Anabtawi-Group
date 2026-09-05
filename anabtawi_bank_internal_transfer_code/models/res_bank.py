# -*- coding: utf-8 -*-
from odoo import fields, models


class ResBank(models.Model):
    _inherit = 'res.bank'

    internal_transfer = fields.Char(
        string='Internal Transfer',
        default='LBT',
    )
