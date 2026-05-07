# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request


def _parse_authorization_bearer(header_value):
    if not header_value:
        return None
    parts = header_value.split(' ', 1)
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None
    token = parts[1].strip()
    return token or None


class AnabtawiMobileAuthController(http.Controller):

    def _eligible_mobile_user(self, user):
        if not user or not user.active:
            return False
        u = user.with_user(user)
        if u.has_group('base.group_public') and not u.has_group('base.group_portal') and not u.has_group('base.group_user'):
            return False
        return u.has_group('base.group_portal') or u.has_group('base.group_user')

    @http.route(
        '/anabtawi/mobile/auth/login',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def mobile_login(self, **kwargs):
        try:
            payload = request.get_json_data() if request.httprequest.is_json else {}
        except Exception:
            payload = {}
        if not payload:
            payload = {
                'login': request.params.get('login'),
                'password': request.params.get('password'),
                'device_uid': request.params.get('device_uid'),
                'device_name': request.params.get('device_name'),
            }
        if not payload and kwargs:
            payload = {k: v for k, v in kwargs.items() if v is not False}

        login_name = (payload.get('login') or '').strip()
        password = payload.get('password') or ''
        device_uid = (payload.get('device_uid') or '').strip()
        device_name = (payload.get('device_name') or '').strip()

        if not login_name or not password:
            return request.make_json_response(
                {'error': 'invalid_request', 'message': _('login and password are required.')},
                status=400,
            )
        if not device_uid:
            return request.make_json_response(
                {'error': 'invalid_request', 'message': _('device_uid is required.')},
                status=400,
            )

        wsgienv = {
            'interactive': False,
            'base_location': request.httprequest.url_root.rstrip('/'),
            'HTTP_HOST': request.httprequest.environ.get('HTTP_HOST', ''),
            'REMOTE_ADDR': request.httprequest.environ.get('REMOTE_ADDR', ''),
        }
        credential = {'type': 'password', 'login': login_name, 'password': password}
        try:
            auth_info = request.env['res.users'].sudo().authenticate(credential, wsgienv)
        except AccessDenied:
            return request.make_json_response(
                {'error': 'access_denied', 'message': _('Invalid login or password.')},
                status=401,
            )

        uid = auth_info['uid']
        user = request.env['res.users'].sudo().browse(uid)
        if not self._eligible_mobile_user(user):
            return request.make_json_response(
                {'error': 'forbidden', 'message': _('This user cannot use the mobile login.')},
                status=403,
            )

        try:
            token_info = request.env['anabtawi.mobile.device'].register_or_refresh_login(
                user, device_uid, device_name
            )
        except UserError as e:
            return request.make_json_response(
                {'error': 'device_mismatch', 'message': e.args[0]},
                status=403,
            )

        return request.make_json_response({
            'status': 'ok',
            'uid': user.id,
            'login': user.login,
            'access_token': token_info['access_token'],
        }, status=200)

    @http.route(
        '/anabtawi/mobile/auth/me',
        type='http',
        auth='public',
        methods=['GET', 'POST'],
        csrf=False,
    )
    def mobile_me(self, **kwargs):
        auth_header = request.httprequest.headers.get('Authorization', '')
        plain = _parse_authorization_bearer(auth_header)
        user = request.env['anabtawi.mobile.device'].authenticate_bearer_token(plain) if plain else request.env['res.users']

        if not user:
            return request.make_json_response(
                {'error': 'unauthorized', 'message': _('Invalid or missing token.')},
                status=401,
            )

        u = user.with_user(user)
        return request.make_json_response({
            'status': 'ok',
            'uid': user.id,
            'login': user.login,
            'is_portal': bool(u.has_group('base.group_portal')),
            'is_internal': bool(u.has_group('base.group_user')),
        }, status=200)

    @http.route(
        '/anabtawi/mobile/ping',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
    )
    def mobile_ping(self, **kwargs):
        auth_header = request.httprequest.headers.get('Authorization', '')
        plain = _parse_authorization_bearer(auth_header)
        user = request.env['anabtawi.mobile.device'].authenticate_bearer_token(plain) if plain else request.env['res.users']
        if not user:
            return request.make_json_response({'error': 'unauthorized'}, status=401)
        return request.make_json_response({
            'status': 'ok',
            'message': 'authenticated',
            'uid': user.id,
        }, status=200)
