# -*- coding: utf-8 -*-
"""Debug logging for /web/login CSRF failures.

CSRF is validated in odoo.http BEFORE any controller runs, so we wrap
Request.validate_csrf to log why the token is rejected.
"""

import logging
import time

from odoo.http import STORED_SESSION_BYTES, Request

_logger = logging.getLogger(__name__)

_original_validate_csrf = Request.validate_csrf


def _is_login_request(request_obj):
    try:
        path = (request_obj.httprequest.path or '').rstrip('/')
        return path.endswith('/web/login')
    except Exception:  # noqa: BLE001 - debug helper must never break requests
        return False


def _logged_validate_csrf(self, csrf):
    if not _is_login_request(self):
        return _original_validate_csrf(self, csrf)

    method = ''
    path = ''
    cookie_session = None
    try:
        method = self.httprequest.method or ''
        path = self.httprequest.path or ''
        cookie_session = self.httprequest.cookies.get('session_id')
    except Exception:  # noqa: BLE001
        pass

    sid = ''
    uid = None
    should_rotate = None
    try:
        sid = self.session.sid or ''
        uid = self.session.uid
        should_rotate = getattr(self.session, 'should_rotate', None)
    except Exception:  # noqa: BLE001
        pass

    sid_prefix = sid[:STORED_SESSION_BYTES] if sid else ''
    cookie_prefix = (cookie_session or '')[:STORED_SESSION_BYTES]

    has_csrf = bool(csrf)
    csrf_prefix = (csrf[:20] + '...') if csrf and len(csrf) > 20 else (csrf or '')
    max_ts = None
    expired = None
    now_ts = int(time.time())
    if csrf:
        _, _, max_ts_str = csrf.rpartition('o')
        try:
            max_ts = int(max_ts_str) if max_ts_str else None
            if max_ts is not None:
                expired = max_ts < now_ts
        except ValueError:
            max_ts = 'invalid'
            expired = True

    # Params still contain csrf_token here only if caller didn't pop yet.
    # Dispatcher pops before calling validate_csrf, so read from raw form too.
    form_keys = []
    has_acting_name = False
    has_acting_password = False
    acting_name = None
    login_value = None
    try:
        form = self.httprequest.form
        form_keys = sorted(form.keys())
        has_acting_name = 'acting_employee_name' in form
        has_acting_password = bool(form.get('acting_employee_password'))
        acting_name = (form.get('acting_employee_name') or '')[:80]
        login_value = (form.get('login') or '')[:80]
    except Exception:  # noqa: BLE001
        pass

    valid = _original_validate_csrf(self, csrf)

    reason = 'ok'
    if not has_csrf:
        reason = 'missing_csrf_token'
    elif expired:
        reason = 'csrf_timestamp_expired'
    elif max_ts == 'invalid':
        reason = 'csrf_timestamp_invalid'
    elif not valid:
        # Most common: session sid changed since the form was rendered.
        if cookie_prefix and sid_prefix and cookie_prefix != sid_prefix:
            reason = 'session_cookie_sid_mismatch'
        else:
            reason = 'csrf_hmac_mismatch_session_rotated_or_stale_form'

    _logger.warning(
        "acting_employee_login CSRF debug: path=%s method=%s valid=%s reason=%s "
        "has_csrf=%s csrf_prefix=%s max_ts=%s expired=%s now_ts=%s "
        "session_sid_prefix=%s cookie_sid_prefix=%s sid_matches_cookie=%s "
        "session_uid=%s should_rotate=%s login=%r acting_name=%r "
        "has_acting_name=%s has_acting_password=%s form_keys=%s",
        path,
        method,
        valid,
        reason,
        has_csrf,
        csrf_prefix,
        max_ts,
        expired,
        now_ts,
        sid_prefix,
        cookie_prefix,
        bool(sid_prefix) and sid_prefix == cookie_prefix,
        uid,
        should_rotate,
        login_value,
        acting_name,
        has_acting_name,
        has_acting_password,
        form_keys,
    )
    return valid


Request.validate_csrf = _logged_validate_csrf
