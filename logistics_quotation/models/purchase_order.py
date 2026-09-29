# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    logistics_request_ids = fields.One2many(
        'logistics.request',
        'purchase_order_id',
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

    def action_open_logistics_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Logistics Requests',
            'res_model': 'logistics.request',
            'view_mode': 'list,form',
            'domain': [('purchase_order_id', '=', self.id)],
            'context': {
                'default_source_type': 'purchase',
                'default_purchase_order_id': self.id,
                'default_company_id': self.company_id.id,
            },
        }
