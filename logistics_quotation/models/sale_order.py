# -*- coding: utf-8 -*-
from odoo import api, fields, models, Command, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    logistics_request_ids = fields.One2many(
        'logistics.request',
        'sale_order_id',
        string='Logistics Requests',
    )
    logistics_count = fields.Integer(
        compute='_compute_logistics_count',
        string='Logistics Count',
    )

    @api.depends('logistics_request_ids')
    def _compute_logistics_count(self):
        for order in self:
            order.logistics_count = len(order.logistics_request_ids)

    def action_request_shipping_cost(self):
        self.ensure_one()

        # Build packaging breakdown items WITHOUT prices
        item_vals = []
        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id):
            weight = (line.product_id.weight or 0.0) * line.product_uom_qty
            volume = (line.product_id.volume or 0.0) * line.product_uom_qty
            item_vals.append(
                Command.create({
                    'product_id': line.product_id.id,
                    'name': line.name or line.product_id.display_name,
                    'quantity': line.product_uom_qty,
                    'product_uom_id': line.product_uom.id,
                    'weight': weight,
                    'volume': volume,
                })
            )

        destination = ""
        if self.partner_shipping_id:
            destination = self.partner_shipping_id._display_address(without_company=True)
        elif self.partner_id:
            destination = self.partner_id._display_address(without_company=True)

        req_vals = {
            'source_type': 'sale',
            'sale_order_id': self.id,
            'company_id': self.company_id.id,
            'destination_address': destination,
            'item_ids': item_vals,
        }
        logistics_req = self.env['logistics.request'].create(req_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Logistics Request'),
            'res_model': 'logistics.request',
            'res_id': logistics_req.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_logistics_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Logistics Requests',
            'res_model': 'logistics.request',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {
                'default_source_type': 'sale',
                'default_sale_order_id': self.id,
                'default_company_id': self.company_id.id,
            },
        }
