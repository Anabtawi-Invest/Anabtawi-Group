# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosOrder(models.Model):
    _inherit = 'pos.order'

    customer_latitude = fields.Float(string='Customer Latitude', digits=(10, 7), copy=False)
    customer_longitude = fields.Float(string='Customer Longitude', digits=(10, 7), copy=False)
    customer_location_captured = fields.Boolean(string='Customer Location Captured', copy=False)
    customer_payment_preference = fields.Selection(
        selection=[
            ('online_card', 'Pay by card online'),
            ('cash_on_delivery', 'Cash on delivery'),
        ],
        string='Payment Preference',
        copy=False,
    )
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
                'customer_payment_preference',
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
            'customer_payment_preference',
        ]
        return fields_list

    @api.model
    def _get_config_from_mobile_order(self, order):
        config_id = order.get('config_id')
        if isinstance(config_id, int):
            return self.env['pos.config'].browse(config_id)
        if isinstance(config_id, (list, tuple)) and config_id:
            return self.env['pos.config'].browse(config_id[0])
        session_id = order.get('session_id')
        if isinstance(session_id, int):
            return self.env['pos.session'].browse(session_id).config_id
        if isinstance(session_id, (list, tuple)) and session_id:
            return self.env['pos.session'].browse(session_id[0]).config_id
        return self.env['pos.config']

    @api.model
    def _validate_mobile_self_order(self, orders):
        for order in orders:
            if order.get('source') != 'mobile':
                continue
            if not order.get('customer_latitude') or not order.get('customer_longitude'):
                raise ValidationError(
                    _('Customer location is required for mobile self-orders.')
                )
            order['customer_location_captured'] = True

            config = self._get_config_from_mobile_order(order)
            if config and config.self_order_require_customer_phone and not order.get('partner_id'):
                raise ValidationError(_('Please verify your phone number before ordering.'))

            if not config or not config.self_order_payment_choice_enabled:
                continue

            preference = order.get('customer_payment_preference')
            if not preference:
                raise ValidationError(_('Please choose how you want to pay.'))
            if preference == 'online_card' and not config.self_order_allow_online_card:
                raise ValidationError(_('Online card payment is not available.'))
            if preference == 'cash_on_delivery' and not config.self_order_allow_cash_on_delivery:
                raise ValidationError(_('Cash on delivery is not available.'))

    @api.model
    def sync_from_ui(self, orders):
        self._validate_mobile_self_order(orders)
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
