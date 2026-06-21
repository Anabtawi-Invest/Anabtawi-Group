# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    visit_id = fields.Many2one(
        'sales.visit',
        string='Originating Visit',
        help="The customer visit from which this sale order/quotation was created."
    )
