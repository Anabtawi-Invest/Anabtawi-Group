# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    advance_payment_id = fields.Many2one(
        'pos.advance.payment',
        string='Advance Payment',
        readonly=True,
        help='Link to advance payment if this order was created from an advance'
    )
    
    is_advance_order = fields.Boolean(
        string='Is Advance Order',
        default=False,
        copy=False,
        help='Indicates if this order was created for an advance payment'
    )

    def _get_invoice_lines_values(self, line_values, pos_line, move_type):
        vals = super()._get_invoice_lines_values(
            line_values, pos_line, move_type
        )

        product = line_values.get('product_id')

        if product and product.name and product.name.strip() == "رهن":
            return {}

        return vals