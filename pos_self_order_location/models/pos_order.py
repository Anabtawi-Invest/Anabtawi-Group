# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosOrder(models.Model):
    _inherit = 'pos.order'

    customer_latitude = fields.Float(string='Customer Latitude', digits=(10, 7), copy=False)
    customer_longitude = fields.Float(string='Customer Longitude', digits=(10, 7), copy=False)
    customer_location_captured = fields.Boolean(string='Customer Location Captured', copy=False)
    self_order_request_id = fields.Many2one(
        'pos.self.order.request',
        string='Self-Order Request',
        copy=False,
        readonly=True,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if fields_list:
            fields_list += [
                'customer_latitude',
                'customer_longitude',
                'customer_location_captured',
                'self_order_request_id',
            ]
        return fields_list

    @api.model
    def _load_pos_self_data_fields(self, config):
        fields_list = super()._load_pos_self_data_fields(config)
        fields_list += [
            'customer_latitude',
            'customer_longitude',
            'customer_location_captured',
        ]
        return fields_list

    @api.model
    def _validate_mobile_self_order_location(self, orders):
        for order in orders:
            if order.get('source') != 'mobile':
                continue
            if not order.get('customer_latitude') or not order.get('customer_longitude'):
                raise ValidationError(
                    _('Customer location is required for mobile self-orders.')
                )
            order['customer_location_captured'] = True

    @api.model
    def sync_from_ui(self, orders):
        self._validate_mobile_self_order_location(orders)
        result = super().sync_from_ui(orders)
        order_ids = self.browse([
            order_data['id']
            for order_data in result.get('pos.order', [])
            if order_data.get('id')
        ])
        mobile_orders = order_ids.filtered(lambda order: order.source == 'mobile')
        request_model = self.env['pos.self.order.request'].sudo()
        for order in mobile_orders:
            request = request_model._sync_from_pos_order(order)
            if request and not order.self_order_request_id:
                order.sudo().write({'self_order_request_id': request.id})
        return result
