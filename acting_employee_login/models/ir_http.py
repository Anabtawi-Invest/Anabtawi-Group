# -*- coding: utf-8 -*-

import logging

from odoo import models
from odoo.http import request

from ..acting_log import _session_snapshot, log_chatter_debug

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)
        cls._log_login_request(rule)
        cls._inject_acting_identity_context()
        cls._log_session_identity_on_requests()

    @classmethod
    def _log_login_request(cls, rule=None):
        if not request or not getattr(request, 'httprequest', None):
            return
        path = (request.httprequest.path or '').rstrip('/')
        if not path.endswith('/web/login'):
            return
        snapshot = _session_snapshot()
        endpoint = getattr(rule, 'endpoint', None) if rule is not None else None
        _logger.warning(
            "acting_employee_login login_request: method=%s path=%s endpoint=%s session=%s",
            request.httprequest.method,
            request.httprequest.path,
            endpoint,
            snapshot,
        )

    @classmethod
    def _inject_acting_identity_context(cls):
        if not request or not getattr(request, 'session', None):
            return
        if not request.session.uid:
            return
        context = {}
        source = None
        if request.session.get('acting_branch_access_id'):
            context.update({
                'acting_branch_access_id': request.session['acting_branch_access_id'],
                'acting_branch_name': request.session.get('acting_branch_name') or '',
            })
            source = 'branch'
        elif request.session.get('acting_employee_id'):
            context.update({
                'acting_employee_id': request.session['acting_employee_id'],
                'acting_employee_name': request.session.get('acting_employee_name') or '',
            })
            source = 'employee'
        if context:
            request.update_context(**context)
            log_chatter_debug(
                'context_injected',
                source=source,
                context=context,
                path=getattr(request.httprequest, 'path', None),
                method=getattr(request.httprequest, 'method', None),
            )

    @classmethod
    def _log_session_identity_on_requests(cls):
        if not request or not getattr(request, 'session', None) or not request.session.uid:
            return
        path = getattr(request.httprequest, 'path', '') or ''
        if '/web/login' in path:
            return
        snapshot = _session_snapshot()
        has_identity = bool(
            snapshot.get('acting_branch_access_id') or snapshot.get('acting_employee_id')
        )
        if has_identity:
            return
        if not any(
            token in path
            for token in ('/web/dataset/call', '/jsonrpc', '/mail/', '/stock')
        ):
            return
        try:
            user = request.env.user
            is_branch_user = bool(getattr(user, 'is_branch_user', False))
        except Exception:  # noqa: BLE001
            is_branch_user = None
            user = None
        if not is_branch_user:
            return
        log_chatter_debug(
            'branch_user_without_session_identity',
            path=path,
            method=getattr(request.httprequest, 'method', None),
            session=snapshot,
            user_id=user.id if user else None,
            login=user.login if user else None,
            hint='User is branch user but session has no acting_branch_access_id. '
                 'Likely logged in without second step (remember device auto-login?)',
        )

    @classmethod
    def _post_logout(cls):
        if request and getattr(request, 'session', None):
            request.session.pop('acting_employee_id', None)
            request.session.pop('acting_employee_name', None)
            request.session.pop('acting_branch_access_id', None)
            request.session.pop('acting_branch_name', None)
        super()._post_logout()
