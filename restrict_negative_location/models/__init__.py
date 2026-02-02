# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockLocation(models.Model):
    _inherit = 'stock.location'

    restrict_negative = fields.Boolean(
        string='Restrict Negative Stock',
        default=False,
        help="If checked, this location will not allow negative stock."
    )


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            location_id = vals.get('location_id')
            quantity = vals.get('quantity', 0)

            if location_id and quantity < 0:
                location = self.env['stock.location'].browse(location_id)
                if location.restrict_negative:
                    raise UserError(
                        _("Negative stock is not allowed for location: %s") % location.display_name
                    )
        return super(StockQuant, self).create(vals_list)

    def write(self, vals):
        if 'quantity' in vals:
            for quant in self:
                new_qty = vals['quantity']
                if new_qty < 0 and quant.location_id.restrict_negative:
                    raise UserError(
                        _("Negative stock is not allowed for location: %s") % quant.location_id.display_name
                    )
        return super(StockQuant, self).write(vals)

