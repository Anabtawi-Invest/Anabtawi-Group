# -*- coding: utf-8 -*-

import logging

from odoo import http, _
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


def _parse_authorization_bearer(header_value):
    if not header_value:
        return None
    parts = header_value.split(' ', 1)
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None
    token = parts[1].strip()
    return token or None


class AnabtawiMobileAuthController(http.Controller):

    def _safe_has_group(self, user, group_xmlid):
        """Use stable language and fail open on group check errors."""
        try:
            return bool(user.sudo().with_context(lang='en_US').has_group(group_xmlid))
        except Exception:
            return False

    def _eligible_mobile_user(self, user):
        if not user or not user.active:
            return False
        if self._safe_has_group(user, 'base.group_system'):
            return False
        is_public = self._safe_has_group(user, 'base.group_public')
        is_portal = self._safe_has_group(user, 'base.group_portal')
        is_internal = self._safe_has_group(user, 'base.group_user')
        if is_public and not is_portal and not is_internal:
            return False
        return is_portal or is_internal

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
        _logger.info(
            "Mobile login request received: login=%s device_uid=%s device_name=%s has_json=%s",
            login_name,
            device_uid,
            device_name,
            bool(request.httprequest.is_json),
        )

        if not login_name or not password:
            _logger.warning("Mobile login rejected: missing login/password login=%s", login_name)
            return request.make_json_response(
                {'error': 'invalid_request', 'message': _('login and password are required.')},
                status=400,
            )
        if not device_uid:
            _logger.warning("Mobile login rejected: missing device_uid login=%s", login_name)
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
            _logger.warning("Mobile login access denied: login=%s", login_name)
            return request.make_json_response(
                {'error': 'access_denied', 'message': _('Invalid login or password.')},
                status=401,
            )

        uid = auth_info['uid']
        user = request.env['res.users'].sudo().browse(uid)
        if not self._eligible_mobile_user(user):
            _logger.warning("Mobile login forbidden by group eligibility: user_id=%s login=%s", user.id, login_name)
            return request.make_json_response(
                {'error': 'forbidden', 'message': _('This user cannot use the mobile login.')},
                status=403,
            )

        try:
            token_info = request.env['anabtawi.mobile.device'].register_or_refresh_login(
                user, device_uid, device_name
            )
        except UserError as e:
            _logger.warning(
                "Mobile login rejected by device policy: user_id=%s login=%s device_uid=%s reason=%s",
                user.id,
                login_name,
                device_uid,
                e.args[0] if e.args else "unknown",
            )
            return request.make_json_response(
                {'error': 'device_mismatch', 'message': e.args[0]},
                status=403,
            )

        _logger.info("Mobile login success: user_id=%s login=%s device_uid=%s", user.id, login_name, device_uid)
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
