# -*- coding: utf-8 -*-

import logging

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)
        cls._log_login_request()
        cls._inject_acting_employee_context()

    @classmethod
    def _log_login_request(cls):
        if not request or not getattr(request, 'httprequest', None):
            return
        path = (request.httprequest.path or '').rstrip('/')
        if not path.endswith('/web/login'):
            return
        sid = ''
        uid = None
        try:
            sid = request.session.sid or ''
            uid = request.session.uid
        except Exception:  # noqa: BLE001
            pass
        cookie_sid = request.httprequest.cookies.get('session_id') or ''
        _logger.warning(
            "acting_employee_login request: method=%s path=%s session_uid=%s "
            "sid_prefix=%s cookie_sid_prefix=%s endpoint=%s",
            request.httprequest.method,
            request.httprequest.path,
            uid,
            sid[:42],
            cookie_sid[:42],
            getattr(rule, 'endpoint', None),
        )

    @classmethod
    def _inject_acting_employee_context(cls):
        if not request or not getattr(request, 'session', None):
            return
        if not request.session.uid:
            return
        acting_id = request.session.get('acting_employee_id')
        if not acting_id:
            return
        request.update_context(
            acting_employee_id=acting_id,
            acting_employee_name=request.session.get('acting_employee_name') or '',
        )

    @classmethod
    def _post_logout(cls):
        if request and getattr(request, 'session', None):
            request.session.pop('acting_employee_id', None)
            request.session.pop('acting_employee_name', None)
        super()._post_logout()
