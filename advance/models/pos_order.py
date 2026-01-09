# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _get_invoice_lines_values(self, line_values, pos_line, move_type):
        vals = super()._get_invoice_lines_values(
            line_values, pos_line, move_type
        )

        product = line_values.get('product_id')
        print("DEBUG PRODUCT:", product)

        if product and product.name and product.name.strip() == "رهن":
            print("SKIP PRODUCT رهن")

            return {}

        return vals