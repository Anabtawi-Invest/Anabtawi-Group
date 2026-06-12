# -*- coding: utf-8 -*-
import logging

from odoo import http, _
from odoo.http import request
from odoo.tools import consteq
from odoo.exceptions import UserError
from werkzeug.exceptions import NotFound, Unauthorized, BadRequest

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController

_logger = logging.getLogger(__name__)


class PosSelfOrderLocationController(http.Controller):

    def _verify_pos_config(self, access_token):
        pos_config = request.env['pos.config'].sudo().search([
            ('access_token', '=', access_token),
            ('self_ordering_mode', '!=', 'nothing'),
        ], limit=1)
        if not pos_config:
            raise NotFound()
        return pos_config

    def _partner_payload(self, partner, config):
        return {
            'res.partner': request.env['res.partner']._load_pos_self_data_read(partner, config),
        }

    def _session_payload(self, session, partner, config, debug_otp=None):
        payload = {
            'session_token': session.token,
            'partner_id': partner.id,
            'phone': session.phone,
            'name': partner.name,
            'partner': self._partner_payload(partner, config),
        }
        if debug_otp:
            payload['debug_otp'] = debug_otp
        return payload

    def _validate_phone(self, phone):
        normalized = request.env['res.partner']._normalize_phone(phone)
        if len(normalized) < 7:
            raise BadRequest(_('Please enter a valid phone number.'))
        return normalized

    @http.route(
        '/pos-self-order/customer/send-otp',
        auth='public',
        type='jsonrpc',
        website=True,
    )
    def customer_send_otp(self, access_token, phone, name=None):
        config = self._verify_pos_config(access_token)
        if not config.self_order_require_customer_phone:
            raise BadRequest(_('Phone verification is disabled for this store.'))
        if not config.self_order_require_phone_otp:
            raise BadRequest(_('OTP verification is disabled for this store.'))

        normalized = self._validate_phone(phone)
        otp = request.env['pos.self.order.phone.otp'].sudo().generate_for_phone(phone, config)
        _logger.info(
            'Self-order OTP for %s on config %s: %s',
            normalized,
            config.display_name,
            otp.code,
        )

        response = {
            'success': True,
            'phone': normalized,
            'expires_in_seconds': 600,
        }
        if config.self_order_otp_show_debug_code:
            response['debug_otp'] = otp.code
        return response

    @http.route(
        '/pos-self-order/customer/verify-otp',
        auth='public',
        type='jsonrpc',
        website=True,
    )
    def customer_verify_otp(self, access_token, phone, code, name=None):
        config = self._verify_pos_config(access_token)
        normalized = self._validate_phone(phone)
        try:
            request.env['pos.self.order.phone.otp'].sudo().verify(phone, code, config)
        except UserError as error:
            raise BadRequest(str(error)) from error

        partner = request.env['res.partner'].sudo().find_or_create_by_phone(
            phone,
            config.company_id,
            name=name,
        )
        if not partner:
            raise BadRequest(_('Could not create customer record.'))

        session = request.env['pos.self.order.customer.session'].sudo().create_session(
            partner,
            config,
            phone,
        )
        return self._session_payload(session, partner, config)

    @http.route(
        '/pos-self-order/customer/identify',
        auth='public',
        type='jsonrpc',
        website=True,
    )
    def customer_identify(self, access_token, phone, name=None):
        config = self._verify_pos_config(access_token)
        if not config.self_order_require_customer_phone:
            raise BadRequest(_('Phone verification is disabled for this store.'))

        partner = request.env['res.partner'].sudo().find_or_create_by_phone(
            phone,
            config.company_id,
            name=name,
        )
        if not partner:
            raise BadRequest(_('Could not create customer record.'))

        session = request.env['pos.self.order.customer.session'].sudo().create_session(
            partner,
            config,
            phone,
        )
        return self._session_payload(session, partner, config)

    @http.route(
        '/pos-self-order/customer/session',
        auth='public',
        type='jsonrpc',
        website=True,
    )
    def customer_session(self, access_token, customer_session_token):
        config = self._verify_pos_config(access_token)
        session = request.env['pos.self.order.customer.session'].sudo().get_valid_session(
            customer_session_token,
            config,
        )
        if not session:
            raise Unauthorized()
        return self._session_payload(session, session.partner_id, config)

    @http.route(
        '/pos-self-order/customer/order-history',
        auth='public',
        type='jsonrpc',
        website=True,
    )
    def customer_order_history(self, access_token, customer_session_token):
        config = self._verify_pos_config(access_token)
        session = request.env['pos.self.order.customer.session'].sudo().get_valid_session(
            customer_session_token,
            config,
        )
        if not session:
            raise Unauthorized()

        orders = request.env['pos.order'].sudo().search([
            ('partner_id', '=', session.partner_id.id),
            ('config_id', '=', config.id),
            ('source', '=', 'mobile'),
        ], order='create_date desc, id desc', limit=50)
        if not orders:
            return {
                'orders': [],
                'statuses': {},
            }

        controller = PosSelfOrderController()
        data = controller._generate_return_values(orders, config)
        statuses = {}
        for order in orders:
            request_rec = order.self_order_request_id
            statuses[order.access_token] = {
                'state': request_rec.state if request_rec else False,
                'name': request_rec.name if request_rec else False,
            }
        data['statuses'] = statuses
        return data

    @http.route(
        '/pos-self-order/location-request-status',
        auth='public',
        type='jsonrpc',
        website=True,
    )
    def get_location_request_status(self, access_token, order_access_token):
        pos_config = self._verify_pos_config(access_token)
        order = request.env['pos.order'].sudo().search([
            ('access_token', '=', order_access_token),
            ('config_id', '=', pos_config.id),
            ('source', '=', 'mobile'),
        ], limit=1)
        if not order or not consteq(order.access_token, order_access_token):
            raise Unauthorized()

        request_rec = order.self_order_request_id
        if not request_rec:
            return {'state': False, 'name': False}

        return {
            'state': request_rec.state,
            'name': request_rec.name,
        }

    @http.route(
        '/pos-self-order/location-request-statuses',
        auth='public',
        type='jsonrpc',
        website=True,
    )
    def get_location_request_statuses(self, access_token, order_access_tokens):
        pos_config = self._verify_pos_config(access_token)
        if not order_access_tokens:
            return {}

        result = {}
        for order_access_token in order_access_tokens:
            order = request.env['pos.order'].sudo().search([
                ('access_token', '=', order_access_token),
                ('config_id', '=', pos_config.id),
                ('source', '=', 'mobile'),
            ], limit=1)
            if not order or not consteq(order.access_token, order_access_token):
                continue

            request_rec = order.self_order_request_id
            result[order_access_token] = {
                'state': request_rec.state if request_rec else False,
                'name': request_rec.name if request_rec else False,
            }
        return result
